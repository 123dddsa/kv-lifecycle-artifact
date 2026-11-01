# GRIEF 同栈基线 vs kvc-lifecycle：实测对比（2026-11-17）

目的：回答审稿人必问的“why not GRIEF”。**结论先行：GRIEF 用崩溃 oracle 在约 8 分钟内确实撞到了同一个目标崩溃，但它没有给出归因、没有保存最小 witness、崩溃后无法继续；kvc-lifecycle 给的是精确 code + 6 动作最小轨迹 + 离线可重放。两者互补，不是替代。**

## 1. 实验设置（同一台机器、同一栈、同一模型）

- 栈：vLLM 0.25.1 + LMCache 0.5.1（engine_driven），Qwen3-0.6B，RTX 4060 Laptop 8GB，WSL2。
- 服务：`run_e2e_conditions.py --server-only`，端口 8051（`evidence/grief_baseline/campaign_smoke1_20261117_184110/server/`）。
- GRIEF：v0.1.0，独立 venv（`evidence/grief_baseline/.venv`），headless `grief run --base-url http://127.0.0.1:8051 --max-iterations 300`；cancellation-heavy seeds。
- kvc-lifecycle：0.8.0，CPU 离线 `kvc check` / 真实组件 replay（同一栈）。
- 原始记录：
  - GRIEF 运行：`evidence/grief_baseline/campaign_long1_20261117/`（`grief_run.log`、`grief_findings/`、`grief_corpus/`）；
  - 服务端日志：`campaign_smoke1_.../server/vllm.log`（目标断言在第 6207/6222 行，时间 19:55:11）；
  - kvc 证据：`tool/examples/vllm_0251_stale_send.jsonl`、`evidence/case_studies/CASE_STUDIES.md`、`evidence/scale_1000/REPORT.md`。

## 2. 实测结果

### GRIEF（300 iters 预算，实际跑了 53 iters 后中止）

- 运行时长：约 **8 分钟**（run 目录 `runs/20261117-114709-3d6ec0`，19:47:09 启动）后，服务端在 **19:55:11** 触发 `assert req_id in self.requests`，EngineCore 崩溃、`EngineDeadError`。
- GRIEF 的 findings：**7 条 / 3 类机制**，分别是：
  - iter 20：`kv_corruption`（输出非确定性，similarity=0.37）；
  - iter 37：`scheduler_hang`（score 8）；
  - iter 44–53：`liveness_failure` ×10（同一 mechanism，score 10）。
- **目标崩溃本身没有被 GRIEF 保存为 finding**：崩溃后服务端连续 10 次 unhealthy，runner 抛 `server has been unhealthy for 10 consecutive iterations` 并中止 campaign（`grief_run.log` 末尾）。即：**它撞到了崩溃，但没有把它归因/记录成 completion-after-free，也没有可继续的见证。**
- witness 状态：findings 里 `"minimized_validation": {"status": "not_minimized"}`——**未最小化**；有候选 trace（context trace_00..09），但没有缩到最小生命周期序列。
- 迭代成本：53 iters / ~482 s ≈ **9.1 s/iter**；到崩溃约 **53 iterations**。

### kvc-lifecycle（同一栈）

- **directed schedule 1 条**（6 个动作）：`START, POLL, ABORT, DELIVER, POLL, DELIVER` → `kvc check` 报 **`I_COMPLETION_AFTER_FREE`**（step 2，free at step 1），exit 1；真实组件 replay 同样命中，单候选耗时约 **7.7 ms**（`real_search_results` 的 `elapsed_ms` 量级）。
- **random 发现成本**：stale 中位 **25 schedules**（1,000-cell 校准，95% CI 23.0–27.5）。
- **离线复现**：0.25.1 录制 trace（5 events）→ `kvc check` 0.2 s 内复现同一 code，**不需要服务端活着**。
- 误报控制：审计 0/214 严格负控；正常负载 FP=0（受控）。

## 3. 对比表

| 维度 | GRIEF（同栈实测） | kvc-lifecycle（同栈实测） |
|---|---|---|
| 是否触及目标崩溃 | **是**：~8 min、~53 iters 后服务端崩溃 | 是：directed 1 schedule；random 中位 25 |
| 崩溃归因 | **否**：7 findings 是 kv_corruption/scheduler_hang/liveness_failure，目标崩溃未保存为 finding | **是**：精确 `I_COMPLETION_AFTER_FREE` + scoped 操作 + step |
| 最小 witness | 否（`not_minimized`；只有候选 trace） | 是：6 动作最小轨迹 + 离线重放 |
| 崩溃后能否继续 | 否：服务端死，campaign 中止 | 是：离线 check 任意已录 trace |
| 误报 | 7 findings/53 iters；其中多数为通用异常类，未在本次独立复核 | 0/214 严格负控；正常负载 0 |
| 接入方式 | 需要跑真实服务、长 campaign | 录 trace 一次 → CI/pytest 回归 |
| 成本口径 | ~9 s/iter，53 iters | 1 schedule（~7.7 ms）或 random 中位 25 schedules |
| family-specific | 否（crash oracle 不区分故障族） | 是（C1–C4 + scoped identity） |

## 4. 结论（写论文用）

1. **不能声称“只有我们能发现这个崩溃”**：同栈上 GRIEF 约 8 分钟就把它撞崩了。任何带取消负载的 crash oracle 都可能撞到。
2. **能声称的是“归因与可回归性”**：GRIEF 报的是通用异常类（三个机制），没有把崩溃归因为 completion-after-free，也没有最小 witness；kvc 给的是精确 code + 6 动作轨迹，且崩溃后仍可离线复现。
3. **定位**：GRIEF 是“找异常”的 fuzzer；kvc 是“把异常变成可审计、可回归的生命周期见证”的契约工具。二者互补：GRIEF 适合发现，kvc 适合定位、最小化、CI 门禁。
4. **Limitations**：单次 GRIEF campaign、单机器、GRIEF 的 7 findings 未逐条独立复核（其中 kv_corruption 依赖 logprob/相似度阈值，可能是误报）；不把“GRIEF 没归因”写成“GRIEF 无能”。
