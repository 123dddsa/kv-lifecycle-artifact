#!/usr/bin/env bash
# Finish the 5090 stack install using the faster Tsinghua PyPI mirror.
set -u
V=${WORKDIR:-.}/venv025
PIP=https://pypi.tuna.tsinghua.edu.cn/simple
LOG=${WORKDIR:-.}/install_5090.log
{
echo "=== FINISH start $(date -u +%FT%TZ) (tsinghua mirror) ==="
echo "=== vllm $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -i "$PIP" "vllm==0.25.1" 2>&1 | tail -5
echo "=== torch runtime deps $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -i "$PIP" \
  "cuda-bindings>=13.0.3,<14" \
  "cuda-toolkit[cublas,cudart,cufft,cufile,cupti,curand,cusolver,cusparse,nvjitlink,nvrtc,nvtx]==13.0.2" \
  "nvidia-cudnn-cu13==9.19.0.56" \
  "nvidia-cusparselt-cu13==0.8.0" \
  "nvidia-nccl-cu13==2.28.9" \
  "nvidia-nvshmem-cu13==3.4.5" \
  "setuptools<82" "triton==3.6.0" 2>&1 | tail -6
echo "=== lmcache $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -i "$PIP" "lmcache==0.5.1" 2>&1 | tail -4
"$V/bin/pip" install -i "$PIP" httpx pytest huggingface_hub 2>&1 | tail -2
echo "=== verify $(date -u +%FT%TZ) ==="
"$V/bin/python" - <<'PY'
import torch
print("torch", torch.__version__, "cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device", torch.cuda.get_device_name(0), "capability", torch.cuda.get_device_capability(0))
    x = torch.randn(2048, 2048, device="cuda"); print("matmul_ok", float((x @ x).sum().item()))
try:
    import vllm; print("vllm", vllm.__version__)
except Exception as e:
    print("vllm_import_fail", repr(e))
try:
    import lmcache; print("lmcache", getattr(lmcache, "__version__", "?"))
except Exception as e:
    print("lmcache_import_fail", repr(e))
PY
echo "=== download Qwen3-0.6B $(date -u +%FT%TZ) ==="
HF_ENDPOINT=https://hf-mirror.com "$V/bin/python" - <<'PY'
from huggingface_hub import snapshot_download
print("model_ok", snapshot_download("Qwen/Qwen3-0.6B", cache_dir="${WORKDIR:-.}/hf"), flush=True)
PY
echo "STACK_DONE $(date -u +%FT%TZ)"
} >> "$LOG" 2>&1

