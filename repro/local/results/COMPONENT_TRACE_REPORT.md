# 0.31 component-level trace：打通报告（task-5）

日期：2026-11-17（Asia/Shanghai）
结论：**vLLM 0.31.0 + LMCache dev 0.5.7.dev96 @90a4ae2f 的 component 级 replay 已打通，2/2 次运行在同一真实断言处命中**；trace 可被 `kvc check` 判为 `I_COMPLETION_AFTER_FREE`（exit 1）。此前 M8 记录的“0.31 component trace 阻塞”已被解除，阻塞原因是 3 处接口漂移（见 §3），不是不可复现。

## 1. 环境 pin（运行时由脚本自报并写入 `run*/stdout.jsonl` 的 environment 事件）

| 项 | 值 |
|---|---|
| vLLM | **0.31.0**（`scheduler.py` sha256 `f820bee4…`，安装于 `<EXPERIMENT_DATA>/venv-vllm031`） |
| LMCache | **0.5.7.dev96**，源码 `<EXPERIMENT_DATA>/LMCache_dev`，git commit **`90a4ae2fe5a02d4065e7a68df316afde8707b953`**（pre-#5938） |
| Python / platform | 3.12.16，WSL2 Linux 6.18.33.2 |
| 真实方法 | worker adapter `submit_retrieve_request` / `get_finished` / `_process_finished_stores`；connector `request_finished` / `build_connector_meta` / `start_load_kv`；scheduler `_free_request` / `_update_from_kv_xfer_finished` |
| 受控边界（脚本自报 `controlled_boundaries`） | transfer completion future；ZMQ/MP request client 与 heartbeat；CUDA IPC event；`finished_req_ids_from_engine` 输入集；fake KV block manager（不分配 GPU 显存） |

`full_engine_gpu_end_to_end=false`：这是 **component-level controlled-I/O** 证据，与 0.25.1 的 gate2/LR_controlled_io 同级，不是 GPU E2E（GPU E2E 证据见 `data/gpu/vllm031/`）。

## 2. 结果（2/2）

| run | 退出码 | 真实 scheduler 断言 | trace | `kvc check` |
|---|---:|---|---|---|
| 4 | **10** | `AssertionError`，`scheduler.py:3157`（`assert req_id in self.requests`） | `trace_component_0_31_run4.jsonl`（4 events） | `I_COMPLETION_AFTER_FREE`，exit **1** |
| 5 | **10** | 同上 | `trace_component_0_31_run5.jsonl`（4 events） | `I_COMPLETION_AFTER_FREE`，exit **1** |

事件序列（真实方法投影，逐行）：
1. `request_finished(delay_free=false)` —— 真实 connector `request_finished` 的返回值；
2. `observe(recving=[req])` —— 真实 worker `get_finished` 报告 receive 完成；
3. `free(req)` —— 真实 `Scheduler._free_request` 执行，`_update_from_kv_xfer_finished` 消费 recv 后由 scheduler 释放；
4. `observe(sending=[req])` —— **释放后**下一步真实 `get_finished` 仍报告 send 完成 → 交给真实 `_update_from_kv_xfer_finished` 命中 `assert req_id in self.requests`。

`results_run4.json` / `results_run5.json` 记录 `reproduced=true`、断言位置与 trace 路径。

## 3. 解除阻塞的 3 处接口漂移（相对 0.25.1 gate2 fixture）

| # | 0.25.1 写法 | 0.31 实际 | 修法 |
|---|---|---|---|
| 1 | `connector_mod.torch_dev.Event/current_stream/stream` | LMCache dev connector 不再持有 `torch_dev`；CUDA ordering event 由 `worker_adapter.create_recorded_event()` 提供 | patch `worker_adapter.create_recorded_event` 返回 MagicMock（本就被列为受控边界） |
| 2 | request 对象可放入 scheduler 的 set | `SimpleNamespace` 定义了 `__eq__` 但无 `__hash__` → `Scheduler._inflight_prefills.discard(request)` 抛 `TypeError: unhashable type: 'HarnessRequest'` | `HarnessRequest.__hash__ = object.__hash__`（身份哈希） |
| 3 | `future.result()` 无参 | `vllm_multi_process_adapter.get_finished` 调用 `r_future.result(timeout=60)` | `ControlledFuture.result(timeout=None)` |

另：0.31 的 `ParallelStrategy(use_mla=…)`→`mla_only=…`、`MessageQueueClient`→`RequestClientFactory.create`+`get_experimental` 两处漂移在原脚本头注释中已处理。

## 4. 与 0.25.1 component trace 的对照

| 维度 | 0.25.1（gate2/LR_controlled_io） | 0.31（本报告） |
|---|---|---|
| 断言位置 | `scheduler.py:2500`，`_update_from_kv_xfer_finished` | `scheduler.py:3157`，同一函数 |
| trace | `tool/examples/vllm_0251_stale_send.jsonl`（5 events，含 quiescence） | 4 events（本 fixture 不声明 quiescence 目标） |
| 判定 | `I_COMPLETION_AFTER_FREE` | 同 |
| 受控边界 | 受控 transfer I/O + fake block manager | 同 + 受控 request client/heartbeat/CUDA IPC event |

**可以写**：同一 completion-after-free 家族在 0.25.1 与 0.31.0 上都可在 component 级受控 I/O 下复现，且是同一个 scheduler 函数、同一断言文本。
**不能写**：0.31 GPU 端到端之外的性能/发生率；不能写 0.31 已修复（dev@90a4ae2f 是 pre-#5938，且 vLLM 侧修复未合并）。

## 5. 复现命令

```bash
# WSL2 Ubuntu
cd <REPO_ROOT>/evidence/component_0_31
VLLM_TARGET_DEVICE=empty KVC_LMCACHE_ROOT=<EXPERIMENT_DATA>/LMCache_dev \
  <EXPERIMENT_DATA>/venv-vllm031/bin/python reproduce_0_31.py --run-id 4
# 期望 exit 10；比较 trace_component_0_31_run4.jsonl 与 run5 一致
```

CPU 侧离线判定（Windows，无需安装）：

```powershell
$env:PYTHONPATH='<REPO_ROOT>\tool\src'
python -m kvc_lifecycle.cli check trace_component_0_31_run4.jsonl   # 期望 exit 1 + I_COMPLETION_AFTER_FREE
```

## 6. 文件

| 文件 | 内容 |
|---|---|
| `reproduce_0_31.py` | 适配后的 fixture（20,761 B，可复现；真实方法调用 + 受控边界显式声明） |
| `run0..run5.stdout.jsonl` | 运行日志（run4/run5 为成功 run；run0–run3 为调试中间态，保留以便审计） |
| `trace_component_0_31_run4.jsonl` / `run5.jsonl` | 两条 4-event trace |
| `results_run4.json` / `results_run5.json` | 判定结果与断言位置 |
| `kvc_check_run4.txt` / `kvc_check_run5.txt` | 离线 checker 输出（exit 1） |

## 7. 边界与诚实声明

- 受控 I/O：completion future、request client、CUDA event、fake block manager 是受控边界；其余生命周期逻辑（adapter/connector/scheduler 真实方法）未打桩。
- 单请求、单 run pair；不声称发生率。
- 0.31 的 GPU E2E 证据独立存在（CS2），本报告不替代它，也不被它替代。
- 测试期间只读 `<EXPERIMENT_DATA>` 下源码与 venv，未改动；所有新增写入都在本目录。
