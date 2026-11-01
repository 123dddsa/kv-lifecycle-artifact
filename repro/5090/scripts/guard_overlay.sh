#!/usr/bin/env bash
# Apply/restore the two-file guard overlay on the pip-installed LMCache 0.5.1
# inside venv025, avoiding the incompatible prebuilt .so of the full fixed tree.
set -u
SP=${WORKDIR:-.}/venv025/lib/python3.12/site-packages/lmcache/integration/vllm
FIXED=${WORKDIR:-.}/work/LMCache_fixed_e2e/lmcache/integration/vllm
FILES="lmcache_mp_connector.py vllm_multi_process_adapter.py"
case "${1:-}" in
  apply)
    for f in $FILES; do
      [ -f "$SP/$f" ] || { echo "missing $SP/$f"; exit 1; }
      [ -f "$SP/$f.kvc_orig" ] || cp -p "$SP/$f" "$SP/$f.kvc_orig"
      cp -f "$FIXED/$f" "$SP/$f"
    done
    ${WORKDIR:-.}/venv025/bin/python -c "import lmcache.integration.vllm.lmcache_mp_connector as c, lmcache.integration.vllm.vllm_multi_process_adapter as a; print('overlay_import_ok', c.__file__)" 2>&1 | tail -2
    ;;
  restore)
    for f in $FILES; do
      [ -f "$SP/$f.kvc_orig" ] && cp -f "$SP/$f.kvc_orig" "$SP/$f"
    done
    echo overlay_restored
    ;;
  *) echo "usage: $0 apply|restore"; exit 2 ;;
esac

