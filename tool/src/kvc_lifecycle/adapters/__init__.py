"""Adapter registry."""

from __future__ import annotations

from pathlib import Path

from .base import ACTIONS, Adapter

__all__ = ["ACTIONS", "Adapter", "make_adapter"]


def make_adapter(
    name: str,
    *,
    root: str | Path | None,
    target: str,
    replay_id: str,
):
    """Create an adapter by name.

    ``vllm-lmcache`` is the only built-in real adapter in M2. It requires a
    checkout containing ``replay_real_traces.py`` (the research harness).
    """

    if name in {"vllm-lmcache", "vllm_lmcache"}:
        from .vllm_lmcache import VLLMLMCacheAdapter

        if root is None:
            raise ValueError("--root is required for the vllm-lmcache adapter")
        return VLLMLMCacheAdapter(root, target, replay_id)
    raise ValueError(f"unknown adapter {name!r}; available: vllm-lmcache")
