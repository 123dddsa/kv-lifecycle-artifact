#!/usr/bin/env bash
# Install the runtime dependencies that the cu130 torch wheel declares, which
# were skipped when torch was installed with --no-deps.
set -u
V=${WORKDIR:-.}/venv025
PIP=https://mirrors.ustc.edu.cn/pypi/simple
LOG=${WORKDIR:-.}/torch_deps.log
{
echo "=== torch deps $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -i "$PIP" \
  "cuda-bindings>=13.0.3,<14" \
  "cuda-toolkit[cublas,cudart,cufft,cufile,cupti,curand,cusolver,cusparse,nvjitlink,nvrtc,nvtx]==13.0.2" \
  "nvidia-cudnn-cu13==9.19.0.56" \
  "nvidia-cusparselt-cu13==0.8.0" \
  "nvidia-nccl-cu13==2.28.9" \
  "nvidia-nvshmem-cu13==3.4.5" \
  "setuptools<82" \
  "triton==3.6.0" 2>&1 | tail -8
echo "=== verify torch cuda $(date -u +%FT%TZ) ==="
"$V/bin/python" - <<'PY'
import torch
print("torch", torch.__version__, "cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device", torch.cuda.get_device_name(0), "capability", torch.cuda.get_device_capability(0))
    x = torch.randn(1024, 1024, device="cuda")
    print("matmul_ok", float((x @ x).sum().item()))
PY
echo "TORCH_DEPS_DONE $(date -u +%FT%TZ)"
} >> "$LOG" 2>&1

