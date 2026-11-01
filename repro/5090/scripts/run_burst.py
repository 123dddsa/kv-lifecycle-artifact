#!/usr/bin/env python3
"""Burst-cancellation experiment: how many simultaneous in-flight cancellations
are needed to hit the completion-after-free race?

Each round launches `concurrency` concurrent streaming requests, lets all of
them reach the response-header stage (in flight), then cancels exactly k of them
and lets the rest complete. A round that causes the target crash ends the trial.

Usage: run_burst.py --burst-k 8 --rounds 3 --concurrency 64
Output: one JSON line on stdout with the incidence result.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
LOGS = Path(os.environ.get("KILL_GATE_E2E_LOG_DIR", str(ROOT / "logs" / "e2e")))
MODEL = os.environ.get("KVC_MODEL", "Qwen/Qwen3-0.6B")
PORT = int(os.environ.get("KILL_GATE_E2E_PORT", "8010"))
BASE_URL = f"http://127.0.0.1:{PORT}"
LOGS.mkdir(parents=True, exist_ok=True)


def emit(event: str, **kwargs) -> None:
    record = {"event": event, "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())}
    record.update(kwargs)
    line = json.dumps(record, sort_keys=True)
    print(line, flush=True)
    with open(LOGS / "driver.log", "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def target_crash() -> bool:
    log = LOGS / "vllm.log"
    if not log.exists():
        return False
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "assert req_id in self.requests" in text


def start_process(name: str, cmd: list[str], env: dict) -> subprocess.Popen[bytes]:
    log = open(LOGS / f"{name}.log", "ab")
    return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                            start_new_session=True)


def stop_process(proc: subprocess.Popen[bytes], name: str) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, 15)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, 9)
    emit("process_stopped", name=name, pid=proc.pid, returncode=proc.poll())


def prompt_for(prefix: int) -> str:
    shared = "KV lifecycle cancellation test. " * 120
    return f"Shared prefix {prefix}: {shared}\nAnswer briefly."


async def wait_health(client: httpx.AsyncClient, proc: subprocess.Popen[bytes], timeout: float = 600) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            response = await client.get("/health", timeout=5)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(2)
    return False


async def complete_one(client: httpx.AsyncClient, request_id: int) -> str:
    try:
        async with client.stream(
            "POST", "/v1/completions",
            json={"model": MODEL, "prompt": prompt_for(request_id % 16),
                  "max_tokens": 64, "temperature": 0, "stream": True},
            timeout=180,
        ) as response:
            async for _ in response.aiter_bytes():
                pass
        return "completed"
    except (httpx.HTTPError, asyncio.TimeoutError) as error:
        emit("request_error", request_id=request_id, error=repr(error))
        return "error"


async def cancel_one(client: httpx.AsyncClient, request_id: int, seed: int, delay_s: float) -> str:
    try:
        async with client.stream(
            "POST", "/v1/completions",
            json={"model": MODEL, "prompt": prompt_for(request_id % 16),
                  "max_tokens": 64, "temperature": 0, "stream": True},
            timeout=30,
        ) as response:
            await asyncio.sleep(delay_s)
        emit("request_cancelled", seed=seed, request_id=request_id, delay_ms=delay_s * 1000)
        return "cancelled"
    except (httpx.HTTPError, asyncio.TimeoutError) as error:
        emit("request_error", request_id=request_id, error=repr(error))
        return "error"


async def run_client(engine: subprocess.Popen[bytes], args) -> int:
    limits = httpx.Limits(max_connections=args.concurrency * 2,
                          max_keepalive_connections=args.concurrency * 2)
    async with httpx.AsyncClient(base_url=BASE_URL, limits=limits) as client:
        if not await wait_health(client, engine, timeout=600):
            emit("burst_result", burst_k=args.burst_k, crashed=False, exit_hint="health")
            return 20
        emit("vllm_ready")
        rng = random.Random(20261119 + args.burst_k)
        for round_id in range(args.rounds):
            cancel_ids = set(rng.sample(range(args.concurrency), args.burst_k))
            delay = rng.uniform(args.dmin, args.dmax)
            tasks = []
            for i in range(args.concurrency):
                if i in cancel_ids:
                    tasks.append(cancel_one(client, i, round_id + 1, delay))
                else:
                    tasks.append(complete_one(client, i))
            outcomes = await asyncio.gather(*tasks)
            await asyncio.sleep(2)
            crashed = target_crash() or engine.poll() is not None
            emit("burst_round", burst_k=args.burst_k, round_id=round_id,
                 cancelled=outcomes.count("cancelled"), completed=outcomes.count("completed"),
                 errors=outcomes.count("error"), crashed=crashed)
            if crashed:
                emit("burst_result", burst_k=args.burst_k, crashed=True, rounds_done=round_id + 1,
                     rounds_planned=args.rounds)
                return 10 if target_crash() else 22
        emit("burst_result", burst_k=args.burst_k, crashed=False, rounds_done=args.rounds,
             rounds_planned=args.rounds)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--burst-k", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.35)
    parser.add_argument("--dmin", type=float, default=0.005)
    parser.add_argument("--dmax", type=float, default=0.300)
    parser.add_argument("--server-only", action="store_true")
    args = parser.parse_args()

    lmcache_exe = Path(sys.executable).with_name("lmcache")
    vllm_exe = Path(sys.executable).with_name("vllm")
    env = os.environ.copy()
    env.setdefault("VLLM_USE_FLASHINFER_SAMPLER", "0")
    env.setdefault("VLLM_ATTENTION_BACKEND", "FLASH_ATTN")
    env["VLLM_WSL2_ENABLE_PIN_MEMORY"] = "1"
    transfer = {
        "kv_connector": "LMCacheMPConnector", "kv_role": "kv_both",
        "kv_connector_module_path": "lmcache.integration.vllm.lmcache_mp_connector",
        "kv_connector_extra_config": {
            "lmcache.mp.host": "127.0.0.1", "lmcache.mp.port": 5555,
            "lmcache.mp.mp_transfer_mode": "engine_driven", "lmcache.mp.mq_timeout": 60,
        },
    }
    lmcache = start_process("lmcache_server", [str(lmcache_exe), "server", "--host", "127.0.0.1",
                                               "--port", "5555", "--http-host", "127.0.0.1",
                                               "--http-port", "8080", "--l1-size-gb", "1",
                                               "--eviction-policy", "LRU"], env)
    time.sleep(3)
    engine = start_process("vllm", [str(vllm_exe), "serve", MODEL, "--served-model-name", MODEL,
                                    "--host", "127.0.0.1", "--port", str(PORT),
                                    "--max-model-len", "4096", "--max-num-seqs", str(args.concurrency),
                                    "--gpu-memory-utilization", str(args.gpu_memory_utilization),
                                    "--no-enable-prefix-caching", "--enforce-eager",
                                    "--kv-transfer-config", json.dumps(transfer)], env)
    try:
        if args.server_only:
            code = 0
        else:
            code = asyncio.run(run_client(engine, args))
    finally:
        stop_process(engine, "vllm")
        stop_process(lmcache, "lmcache_server")
        emit("e2e_cleanup_complete")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

