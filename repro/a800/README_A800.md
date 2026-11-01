# A800 reproducibility notes (rate matrix + 8B)

Companion to the 5090 bundle. Host credentials and SSH helpers are not included.

## Host

- NVIDIA A800 80GB PCIe, driver 580.82.07, CUDA 12.8 (no nvcc on system PATH by
  default), Ubuntu 22.04.5, ~1TB RAM, 50GB data disk mounted at `<WORKDIR>`.
  `push`, `pull`).

## Environment build (what was actually done)

```bash
# 1) venv
<PYTHON>/bin/python -m venv <WORKDIR>/venv025

# 2) torch 2.11.0+cu130 from SJTU's pytorch-wheels mirror.
#    Pitfall: curl saved wheels with a literal %2B in the filename; pip then
#    failed with ENOENT. Rename %2B -> + before installing:
#    torch-2.11.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl
venv025/bin/pip install --no-deps \
  <WORKDIR>/wheels/torch-2.11.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl

# 3) vLLM 0.25.1 + LMCache 0.5.1 (USTC PyPI mirror; aliyun used for lmcache
#    because USTC redirects lmcache to 403 for some versions)
venv025/bin/pip install -i https://mirrors.ustc.edu.cn/pypi/simple vllm==0.25.1
venv025/bin/pip install -i https://mirrors.aliyun.com/pypi/simple lmcache==0.5.1
venv025/bin/pip install httpx pytest huggingface_hub flashinfer-cubin==0.6.13

# 4) models (HF mirror; 8B is 16GB and fits the 50GB data disk with the 0.6B)
HF_ENDPOINT=https://hf-mirror.com venv025/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("Qwen/Qwen3-0.6B", cache_dir="<WORKDIR>/hf")
snapshot_download("Qwen/Qwen3-8B", cache_dir="<WORKDIR>/hf8b")
PY
```

## Layout

```
<WORKDIR>/
  venv025/      # vLLM 0.25.1 + LMCache 0.5.1 + torch 2.11.0+cu130
  hf/           # Qwen3-0.6B
  hf8b/         # Qwen3-8B (16GB)
  work/         # scripts (this bundle)
  work/scripts/run_e2e_conditions.py   # e2e driver used by rate_matrix
  work/LMCache_fixed_e2e/              # guard fixed tree (two patched .py files)
  results/      # W0..W7, SMOKE, progress.txt, queue.log
```

## Experiments

```bash
# W0-W5 rate matrix (original stack + guard variants)
bash <WORKDIR>/work/run_rate_matrix.sh
# W6/W7: 8B rates (queued after the matrix)
bash <WORKDIR>/work/run_queue_after_matrix.sh
# single-chain variant used in the final overnight run
bash <WORKDIR>/work/run_overnight.sh
```

Key driver: `rate_matrix.py` (`--variant original|fixed`, `--concurrency`,
`--dmin/--dmax`, `--reps`, `--rounds`, `--model`, `--hf-home`). It starts the
e2e driver per rep, records exit code, target assertion, and wall time, and
writes `rate_results.json` / `rate_rows.csv` per condition.

## Results (valid)

| Condition | reps | crashes | rate | Wilson 95% CI | median wall |
|---|---:|---:|---:|---|---:|
| W0 original c=64, cancel 5-300ms | 20 | 20 | 100% | 83.9-100% | 67.5s |
| W1 original c=1, cancel 5-300ms | 20 | 20 | 100% | 83.9-100% | 78.5s |
| W2 original c=8, cancel 5-300ms | 20 | 20 | 100% | 83.9-100% | 72.4s |
| W3 original c=64, cancel 0-30ms | 20 | 20 | 100% | 83.9-100% | 74.3s |
| W6 Qwen3-8B c=64, cancel 5-300ms | 12 | 12 | 100% | 75.8-100% | 78.8s |
| W7 Qwen3-8B c=1, cancel 5-300ms | 12 | 12 | 100% | 75.8-100% | 74.4s |

Invalid (do not use): W4/W5 guard variants, all 15 reps exit 24
(`lmcache_server_start_failed`) because the fixed tree's prebuilt `.so` requires
`CXXABI_1.3.15`, absent on this container; `rate_results.json` then reports
`crashes: 0`, which is a false negative of the harness, not a guard result.
The guard negative was later obtained on the 5090 with the two-file overlay.

Raw data: `results/conditions/W*/rate_results.json` + `rate_rows.csv`;
overnight summary in `results/SUMMARY.md`.

## Pitfalls

1. **Model override for 8B**: the first version of `rate_matrix.py --model`
   wrote `work/logs/model_snapshot_path.txt`, but the driver reads
   `work/scripts/logs/model_snapshot_path.txt`, so W6/W7 silently ran the 0.6B
   model. Fixed by passing `KVC_MODEL` through the driver environment
   (`MODEL = os.environ.get("KVC_MODEL", "Qwen/Qwen3-0.6B")`) and removing the
   file-based override. All W6/W7 rows before the fix were deleted.
2. **LMCache 5555 port**: every trial starts its own LMCache server; a crashed
   trial can leave it alive and the next trial then fails start-up. Reap
   leftovers between trials.
3. **`pkill -f` self-match**: patterns like `pkill -f "lmcache server"` match
   the invoking shell (the pattern string is in its command line) and kill the
   SSH session. Use `ps aux | grep -E "[l]mcache server"` or build the pattern
   via `printf`.
4. **SSH long-run watchers**: a paramiko channel dies after ~1h, so long waits
   must run as remote `nohup` jobs and be polled with short commands.
5. **Disk**: 50GB forces serialized installs; delete the 8B model before
   installing another stack.