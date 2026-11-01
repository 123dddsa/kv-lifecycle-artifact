#!/usr/bin/env bash
# Install the pinned 0.25.1 stack on the rented RTX 5090 (Blackwell, Ubuntu 22.04).
# venv + models live on the 50GB data disk ${WORKDIR:-.}.
set -u
M=${WORKDIR:-.}
V=$M/venv025
LOG=$M/install_5090.log
PIP="https://mirrors.ustc.edu.cn/pypi/simple"
TORCH_BASE="https://mirrors.sjtug.sjtu.edu.cn/pytorch-wheels/cu130"
mkdir -p "$M" "$M/hf" "$M/work"

echo "=== install start $(date -u +%FT%TZ) ==="
${PYTHON:-python3}/bin/python -m venv "$V" || { echo VENV_FAIL; exit 1; }
"$V/bin/python" -m pip install -q --upgrade pip -i "$PIP" || echo PIP_UPGRADE_WARN

echo "=== torch stack $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -q --no-deps \
  "$TORCH_BASE/torch-2.11.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl" \
  "$TORCH_BASE/torchvision-0.26.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl" \
  "$TORCH_BASE/torchaudio-2.11.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl" || { echo TORCH_FAIL; exit 1; }

echo "=== torch deps $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -q -i "$PIP" filelock typing-extensions sympy networkx jinja2 fsspec numpy pillow || echo TORCH_DEPS_WARN

echo "=== vllm 0.25.1 $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -q -i "$PIP" "vllm==0.25.1" || { echo VLLM_FAIL; exit 1; }

echo "=== lmcache 0.5.1 $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -q -i "$PIP" "lmcache==0.5.1" || { echo LMCACHE_FAIL; exit 1; }

echo "=== extras $(date -u +%FT%TZ) ==="
"$V/bin/pip" install -q -i "$PIP" httpx pytest huggingface_hub || echo EXTRAS_WARN

echo "=== verify $(date -u +%FT%TZ) ==="
"$V/bin/python" - <<'PY'
import torch, vllm, lmcache
print("stack_ok", torch.__version__, vllm.__version__, getattr(lmcache, "__version__", "?"),
      "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
PY

echo "=== download Qwen3-0.6B $(date -u +%FT%TZ) ==="
HF_ENDPOINT=https://hf-mirror.com "$V/bin/python" - <<'PY'
from huggingface_hub import snapshot_download
p = snapshot_download("Qwen/Qwen3-0.6B", cache_dir="${WORKDIR:-.}/hf")
print("model_ok", p, flush=True)
PY
echo "STACK_DONE $(date -u +%FT%TZ)"

