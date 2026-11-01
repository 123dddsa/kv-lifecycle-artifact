#!/usr/bin/env python3
"""Real vLLM + LMCache MP streaming-cancellation end-to-end experiment."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parent
LOGS = Path(os.environ.get("KILL_GATE_E2E_LOG_DIR", str(ROOT / "logs" / "e2e")))
MODEL = "Qwen/Qwen3-0.6B"
PORT = int(os.environ.get("KILL_GATE_E2E_PORT", "8010"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def emit(event: str, **fields: object) -> None:
    record = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)


def start_process(name: str, command: list[str], env: dict[str, str]) -> subprocess.Popen[bytes]:
    log_path = LOGS / f"{name}.log"
    handle = log_path.open("wb")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    emit("process_started", name=name, pid=process.pid, pgid=os.getpgid(process.pid), command=command)
    return process


def stop_process(name: str, process: subprocess.Popen[bytes] | None) -> None:
    if process is None:
        return
    # start_new_session makes the child PID its process-group ID. Signal the
    # group even if the parent already exited, so EngineCore children cannot leak.
    pgid = process.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
    emit("process_stopped", name=name, pid=process.pid, pgid=pgid, returncode=process.returncode)


def target_crash() -> bool:
    path = LOGS / "vllm.log"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    # Other EngineCore failures (OOM, startup, unrelated bugs) are not target hits.
    return "assert req_id in self.requests" in text


async def wait_health(client: httpx.AsyncClient, process: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            emit("vllm_exited_during_startup", returncode=process.returncode)
            return False
        try:
            response = await client.get("/health", timeout=2.0)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(2.0)
    return False


def prompt_for(prefix: int) -> str:
    shared = "KV lifecycle cancellation test. " * 120
    return f"Shared prefix {prefix}: {shared}\nAnswer briefly."


async def normal_request(client: httpx.AsyncClient, tag: str) -> bool:
    try:
        response = await client.post(
            "/v1/completions",
            json={"model": MODEL, "prompt": prompt_for(0), "max_tokens": 8, "temperature": 0},
            timeout=120,
        )
    except httpx.HTTPError as error:
        emit("normal_request_error", tag=tag, error=repr(error), target_crash=target_crash())
        return False
    emit("normal_request", tag=tag, status=response.status_code, body=response.text[:500])
    return response.status_code == 200


async def metrics_snapshot(client: httpx.AsyncClient, tag: str) -> None:
    try:
        response = await client.get("/metrics", timeout=5)
    except httpx.HTTPError as error:
        emit("metrics_error", tag=tag, error=repr(error))
        return
    values = {}
    for line in response.text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if "cache_usage" in name or "num_requests" in name:
            values[name] = parts[1]
    emit("metrics_snapshot", tag=tag, values=values)


async def cancel_one(client: httpx.AsyncClient, request_id: int, seed: int) -> str:
    delay_min = float(os.environ.get("KILL_GATE_CANCEL_DELAY_MIN", "0.005"))
    delay_max = float(os.environ.get("KILL_GATE_CANCEL_DELAY_MAX", "0.300"))
    delay = random.Random(seed * 10000 + request_id).uniform(delay_min, delay_max)
    started = time.perf_counter()
    try:
        async with client.stream(
            "POST",
            "/v1/completions",
            json={
                "model": MODEL,
                "prompt": prompt_for(request_id % 16),
                "max_tokens": 64,
                "temperature": 0,
                "stream": True,
            },
            timeout=30,
        ) as response:
            await asyncio.sleep(delay)
        elapsed_ms = (time.perf_counter() - started) * 1000
        emit("request_cancelled", seed=seed, request_id=request_id, delay_ms=delay * 1000, elapsed_ms=elapsed_ms)
        return "cancelled"
    except (httpx.HTTPError, asyncio.TimeoutError) as error:
        emit("request_error", seed=seed, request_id=request_id, error=repr(error))
        return "error"


async def run_client(vllm: subprocess.Popen[bytes], rounds: int, concurrency: int) -> int:
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency * 2)
    async with httpx.AsyncClient(base_url=BASE_URL, limits=limits) as client:
        if not await wait_health(client, vllm, timeout=600):
            return 20
        emit("vllm_ready")
        await metrics_snapshot(client, "baseline")
        if not await normal_request(client, "pre-cancel"):
            return 21
        await metrics_snapshot(client, "after_pre_cancel")
        for round_id in range(rounds):
            outcomes = await asyncio.gather(
                *(cancel_one(client, i, round_id + 1) for i in range(concurrency))
            )
            await asyncio.sleep(2)
            await metrics_snapshot(client, f"round_{round_id}_after_cancel")
            crashed = target_crash() or vllm.poll() is not None
            emit(
                "cancel_round",
                round_id=round_id,
                outcomes={name: outcomes.count(name) for name in set(outcomes)},
                vllm_returncode=vllm.poll(),
                target_crash=crashed,
            )
            if crashed:
                return 10 if target_crash() else 22
            if not await normal_request(client, f"post-cancel-{round_id}"):
                return 10 if target_crash() else 23
            await metrics_snapshot(client, f"round_{round_id}_after_normal")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.35)
    parser.add_argument(
        "--server-only",
        action="store_true",
        help="Start the unchanged service stack and wait for an external client; cleanup on SIGINT.",
    )
    args = parser.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["HF_HOME"] = os.environ.get("HF_HOME", str(ROOT / "cache" / "huggingface"))
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["VLLM_LOGGING_LEVEL"] = "INFO"
    python = Path(sys.executable)
    lmcache = python.parent / "lmcache"
    vllm_exe = python.parent / "vllm"
    server = None
    engine = None
    try:
        import socket

        server = start_process(
            "lmcache_server",
            [
                str(lmcache), "server", "--host", "127.0.0.1", "--port", "5555",
                "--http-host", "127.0.0.1", "--http-port", "8080",
                "--l1-size-gb", "1", "--eviction-policy", "LRU",
            ],
            env,
        )
        deadline = time.monotonic() + 600
        while True:
            if server.poll() is not None:
                emit("lmcache_server_start_failed", returncode=server.returncode)
                return 24
            try:
                with socket.create_connection(("127.0.0.1", 5555), timeout=1):
                    pass
                emit("lmcache_server_ready")
                break
            except OSError:
                if time.monotonic() >= deadline:
                    emit("lmcache_server_start_timeout")
                    return 24
                time.sleep(2)
        transfer_config = {
            "kv_connector": "LMCacheMPConnector",
            "kv_role": "kv_both",
            "kv_connector_module_path": "lmcache.integration.vllm.lmcache_mp_connector",
            "kv_connector_extra_config": {
                "lmcache.mp.host": "127.0.0.1",
                "lmcache.mp.port": 5555,
                "lmcache.mp.mp_transfer_mode": "engine_driven",
                "lmcache.mp.mq_timeout": 60,
            },
        }
        engine = start_process(
            "vllm",
            [
                str(vllm_exe), "serve",
                str((ROOT / "logs" / "model_snapshot_path.txt").read_text(encoding="utf-8").strip())
                if (ROOT / "logs" / "model_snapshot_path.txt").exists() else MODEL,
                "--served-model-name", MODEL,
                "--host", "127.0.0.1", "--port", str(PORT),
                "--max-model-len", "4096", "--max-num-seqs", str(args.concurrency),
                "--gpu-memory-utilization", str(args.gpu_memory_utilization),
                "--no-enable-prefix-caching", "--enforce-eager",
                "--kv-transfer-config", json.dumps(transfer_config),
            ],
            env,
        )
        if args.server_only:
            async def serve_external_client() -> int:
                async with httpx.AsyncClient(base_url=BASE_URL) as client:
                    if not await wait_health(client, engine, timeout=600):
                        return 20
                emit("server_only_ready", base_url=BASE_URL)
                return await asyncio.to_thread(engine.wait)

            return asyncio.run(serve_external_client())
        return asyncio.run(run_client(engine, args.rounds, args.concurrency))
    except KeyboardInterrupt:
        emit("server_only_interrupted")
        return 130
    except Exception as error:
        emit("e2e_harness_error", error=repr(error))
        return 99
    finally:
        stop_process("vllm", engine)
        stop_process("lmcache_server", server)
        emit("e2e_cleanup_complete")


if __name__ == "__main__":
    raise SystemExit(main())

