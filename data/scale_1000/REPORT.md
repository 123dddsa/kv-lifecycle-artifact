# 1,000-cell/族 外部校准（Phase 0，2026-11-17）

目的：把成本律的外部校准样本从 200 cells/族扩到 **1,000 cells/族**（来自 200-cell 的 5 倍），收窄中位 CI，并检验“26.5 是否只是抽样噪声”。

## 配置

- harness：真实 LMCache/vLLM connector/scheduler 方法 + 受控 I/O（与 `experiments/real_200` 完全同源）；`VLLM_TARGET_DEVICE=empty`，CPU 侧组件回放。
- seeds：**1000–1999**（与旧 20–219 不重叠）；每 target 1,000 random cells + 1,000 directed repeats。
- 预算：每 cell ≤200 schedules、≤10 actions；命中即停；右删失记 201。
- 规模：6,000 cells；**45,526 candidate schedules；436,277 真实组件 actions**；`harness_errors=0`、`target_mismatches=0`。
- 原始数据：`real_search_by_seed.csv`、`real_search_results.json`、`real_search_trajectories.jsonl`（22 MB）、`driver.log`（222 MB，含逐 action 事件）。
- 分析脚本：`analyze_scale_1000.py`；结果：`scale_1000_analysis.json`。

## 结果（random arm）

| target | 1,000-cell 中位（bootstrap 95% CI） | 200-cell 中位（95% CI） | 预测中位 | 候选级 q（Wilson 95%） | DP q |
|---|---|---|---:|---|---:|---|
| stale_send | **25.0（23.0–27.5）** | 26.5（22–32） | **25** | 0.02800（0.02634–0.02976） | 0.02792  |
| dual_completion | **2.0（2.0–2.0）** | 2.0（2–3） | **2** | 0.37893（0.36061–0.39760） | 0.37554  |
| permanent_proc | **3.0（3.0–3.0）** | 3.0（2–3） | **3** | 0.23557（0.22305–0.24857） | 0.22593  |

- 发现率：stale **998/1000**（2 个右删失）、dual **1000/1000**、PROC **1000/1000**；Wilson 95% 下界 0.9927。
- directed policy：三个 target 全部 **1 schedule** 命中（1,000/1,000）。
- 结论：**200-cell 的 26.5 是中位抽样噪声**；样本扩到 1,000 后中位精确回到预测值 25，CI 从 [22,32] 收窄到 [23,27.5]。这是对“成本律是外部校准规律”的更强证据，而不是口径调整。
- `code_set_mismatches=2709`（全部集中在 stale random 的 legacy delay-free 误报路径，与 200-cell 的 533 同源；`all_candidates_target_match=true`），不影响 target 判定，已在 `experiments/COMPLETION_REPORT.md` 记录为已知 legacy 误报。

## 与 200-cell 的对比

| target | 200-cell 中位 | 1,000-cell 中位 | 预测 | 结论 |
|---|---|---|---:|---|
| stale_send | 26.5（22–32） | **25.0（23–27.5）** | 25  |
| dual_completion | 2.0（2–3） | **2.0（2–2）** | 2  |
| permanent_proc | 3.0（2–3） | **3.0（3–3）** | 3  |

## 边界（不变）

- 受控 I/O、单一 harness、uniform 策略、`w=0, H=10`；不是生产发生率。
- `directed` 是研究者写的 target-conditioned 策略，不是通用搜索算法；其 1-schedule 命中用于对照 rarity，不用于声称“搜索很快”。
- 2 个 stale cell 右删失；中位数按删失值 201 计入（与旧分析同约定）。

## 复现

```bash
cd <MOUNT><HOME>/<DATA>/<LOCAL_WORKSPACE>
VLLM_TARGET_DEVICE=empty .venv-gpu/bin/python search_real_components.py \
  --seeds "$(seq -s, 1000 1999)" --max-schedules 200 --max-steps 10 \
  --output .../scale_1000/real_search_results.json \
  --csv .../scale_1000/real_search_by_seed.csv \
  --trajectories .../scale_1000/real_search_trajectories.jsonl
python .../evidence/scale_1000/analyze_scale_1000.py
```

The reported quantities are medians, bootstrap intervals, and candidate-level hit-rate intervals. We do not report a KS statistic here: first-discovery counts live on a discrete support with ties and censoring, where the continuous-KS p-value is not meaningful.
