# Reproducibility bundle: KV lifecycle contracts on rented GPUs

**Portability.** Scripts take machine-specific paths from environment variables: `WORKDIR` (scratch dir with venv/results), `REPO` (this bundle root), `LOCAL_WORKSPACE` and `DATA_DIR` (host-side experiment data). Set them before running, e.g. `export WORKDIR=$HOME/kv-work REPO=$PWD`. No absolute path is hard-coded.

Everything needed to replay the GPU evidence in this paper. Two hosts were used:

| Host | Hardware | Role |
|---|---|---|
| `5090` (rented cloud) | RTX 5090 32GB, driver 595.71.05, Ubuntu 22.04, 128 cores, 754GB RAM, 50GB data disk | smoke, guard overlay, incidence, burst, cross-hardware rate |
| `A800` (rented cloud) | A800 80GB PCIe, driver 580.82.07, Ubuntu 22.04, 50GB data disk | rate matrix W0–W3, 8B W6/W7 |
| local | RTX 4060 Laptop 8GB, WSL2 | GRIEF baseline, calibration campaigns, offline `kvc check` (see `local/README_LOCAL.md`) |

## 1. Environment (5090)

```bash
# base: Ubuntu 22.04 + miniconda python 3.12.3
<PYTHON>/bin/python -m venv <WORKDIR>/venv025

# torch cu130 from SJTU mirror (wheels verified by HEAD:
#   torch-2.11.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl, 531146695 bytes)
TORCH_BASE=https://mirrors.sjtug.sjtu.edu.cn/pytorch-wheels/cu130
venv025/bin/pip install --no-deps \
  "$TORCH_BASE/torch-2.11.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl" \
  "$TORCH_BASE/torchvision-0.26.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl" \
  "$TORCH_BASE/torchaudio-2.11.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl"

# runtime deps that --no-deps skipped (exact pins from the torch wheel metadata)
venv025/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  "cuda-bindings>=13.0.3,<14" \
  "cuda-toolkit[cublas,cudart,cufft,cufile,cupti,curand,cusolver,cusparse,nvjitlink,nvrtc,nvtx]==13.0.2" \
  "nvidia-cudnn-cu13==9.19.0.56" "nvidia-cusparselt-cu13==0.8.0" \
  "nvidia-nccl-cu13==2.28.9" "nvidia-nvshmem-cu13==3.4.5" \
  "setuptools<82" "triton==3.6.0"

# vLLM 0.25.1 + LMCache 0.5.1 + client deps
venv025/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  "vllm==0.25.1" "lmcache==0.5.1" httpx pytest huggingface_hub modelscope

# model: hf-mirror's Xet downloader hangs on this instance, so use ModelScope
venv025/bin/python - <<'PY'
from modelscope import snapshot_download
print(snapshot_download("Qwen/Qwen3-0.6B", cache_dir="<WORKDIR>/hf_ms"))
PY
# -> <WORKDIR>/hf_ms/models/Qwen--Qwen3-0.6B/snapshots/master
```

Pinned environment snapshot: `pip_freeze.txt` (230 lines; contains torch 2.11.0+cu130, vllm 0.25.1, lmcache 0.5.1, transformers 5.23.0, triton 3.6.0, flashinfer 0.6.13).

## 2. Paths and env vars used by every experiment

```bash
B=<WORKDIR>
V=$B/venv025/bin/python
M=$B/hf_ms/models/Qwen--Qwen3-0.6B/snapshots/master   # local model path
export KVC_MODEL=$M
export VLLM_USE_FLASHINFER_SAMPLER=0      # REQUIRED on sm_120, see §5
export VLLM_ATTENTION_BACKEND=FLASH_ATTN  # REQUIRED on sm_120
export HF_HOME=$B/hf
```

`$B/work/` holds the scripts; `$B/results/` holds raw outputs. Logs are appended per process; each trial's `driver.log`, `vllm.log`, `lmcache_server.log` live in `results/<experiment>/trialNN/`.

## 3. Experiment order and commands

```bash
# (a) smoke: one cancellation round must reproduce the target assertion
KVC_MODEL=$M bash $B/work/smoke_5090.sh
# expect: SMOKE_RESULT rc=10 target_assertion=true ... ; SMOKE_DONE ok

# (b) guard overlay: apply the two-file guard patch, run 6-round negatives
bash $B/work/run_guard_overlay.sh
# expect: results/guard_overlay/guard_rows.jsonl -> target_assertion=false, exit=0

# (c) incidence matrix: mixed traffic + 0/0.1/0.5/1/5% cancellation (43 trials)
KVC_MODEL=$M bash $B/work/run_incidence_matrix.sh
# expect: results/incidence/incidence_rows.jsonl (control_p0 must be crashed=false)

# (d) burst matrix: k simultaneous in-flight cancellations x 8 trials (k=1,4,16,64)
bash $B/work/run_burst_matrix.sh
# expect: results/burst/burst_rows.jsonl

# (e) cross-hardware rate: c=64, 12 reps, 5-300ms cancel delay
KVC_MODEL=$M $V $B/work/rate_matrix.py --variant original --model "$M" --hf-home $B/hf \
  --concurrency 64 --dmin 0.005 --dmax 0.300 --reps 12 --rounds 6 \
  --outdir $B/results/W0_5090_c64_5-300
# expect: rate_results.json -> crash_rate 1.0 (12/12)

# (f) package + pull
bash $B/work/finalize_results.sh
# copy results/*.jsonl, results/*.json, and the SUMMARY files back from the rented host
```

The full overnight order is encoded in `run_5090_chain.sh` and `run_5090_extras.sh`.

## 4. Files in this bundle

- `5090/scripts/install_5090.sh`, `finish_5090.sh`, `torch_deps_5090.sh` — environment build (including the mirror switch and the `--no-deps` recovery).
- `5090/scripts/smoke_5090.sh` — one-round reproduce-or-stop gate.
- `5090/scripts/guard_overlay.sh`, `run_guard_overlay.sh` — two-file guard patch + negative trials.
- `5090/scripts/run_incidence.py`, `run_incidence_matrix.sh` — mixed-traffic incidence client and matrix.
- `5090/scripts/run_burst.py`, `run_burst_matrix.sh` — burst-cancellation client and matrix.
- `5090/scripts/rate_matrix.py`, `scripts_run_e2e_conditions.py` — A800/5090 rate matrix driver + e2e client.
- `5090/scripts/finalize_results.sh` — packaging.
- `tla/` (repository root) — TLA+ models and TLC configs.
- `5090/pip_freeze.txt` — exact installed versions.
- Logs: `../5090_results/` (status, guard/incidence rows), `tla/TLC_*.log` (repository root).

## 5. Pitfalls encountered (and fixes)

1. **FlashInfer on sm_120**: FlashInfer 0.6.13's `check_cuda_arch` rejects Blackwell (`requires sm75 or higher`), so vLLM with default sampler fails EngineCore init (exit 20). Fix: `VLLM_USE_FLASHINFER_SAMPLER=0` and `VLLM_ATTENTION_BACKEND=FLASH_ATTN`. The smoke works without the backend override; the mixed-traffic client must set both.
2. **hf-mirror + hf-xet hangs** on model download (stalled at 8/10 files, 21MB). Fix: use ModelScope (`snapshot_download`) and pass the local snapshot path as `KVC_MODEL`.
3. **guard fixed tree ABI**: the prebuilt `.so` in the full fixed tree needs `CXXABI_1.3.15`, unavailable on Ubuntu 22.04 → LMCache CLI degrades and rejects `--http-host/--http-port`. Fix: copy only the two patched `.py` files over the pip-installed LMCache (`guard_overlay.sh apply`), and restore afterwards (`restore`).
4. **port 5555 reuse**: every trial starts its own LMCache server on 5555; stale servers must be reaped between trials (the drivers stop their children; if a trial is killed externally, kill leftovers before the next run).
5. **pip resolver churn**: installing `vllm==0.25.1` with the USTC mirror took ~40 min because the resolver downloaded the full CUDA 13 set; Tsinghua was ~3x faster. The `--no-deps` torch install requires the explicit runtime-dep step in §1.
6. **running from a non-UTF-8 console**: all scripts emit JSON lines; keep `LC_ALL=C.UTF-8` if piping to parsers.



