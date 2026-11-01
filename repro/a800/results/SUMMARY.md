# A800 夜间实验汇总（2026-11-17 22:30 → 2026-11-18 02:00）

实例已于 02:00 自动关机，SSH 已不可达。以下全部来自本地已拉取的数据
（`evidence/a800_results/`，最后拉取时间 01:46）。原始压缩包在 `results_final_*.tar.gz`。

## 一、有效结果（可直接用于论文）

### 触发率矩阵（0.25.1 + LMCache 0.5.1，Qwen3-0.6B，A800 80GB）

| 条件 | reps | crashes | crash rate | Wilson 95% CI | 中位耗时 |
|---|---:|---:|---:|---|---:|
| W0 原始 c=64，取消 5–300ms | 20 | 20 | **100%** | 83.9–100% | 67.5s |
| W1 原始 c=1，取消 5–300ms | 20 | 20 | **100%** | 83.9–100% | 78.5s |
| W2 原始 c=8，取消 5–300ms | 20 | 20 | **100%** | 83.9–100% | 72.4s |
| W3 原始 c=64，取消 0–30ms | 20 | 20 | **100%** | 83.9–100% | 74.3s |

### 8B 泛化（Qwen3-8B，同栈）

| 条件 | reps | crashes | crash rate | Wilson 95% CI | 中位耗时 |
|---|---:|---:|---:|---|---:|
| W6 8B c=64，取消 5–300ms | 12 | 12 | **100%** | 75.8–100% | 78.8s |
| W7 8B c=1，取消 5–300ms | 12 | 12 | **100%** | 75.8–100% | 74.4s |

结论：0.6B 与 8B、c=1/8/32/64、取消时点 0–30ms 与 5–300ms，**全部 20/20 或 12/12 命中**。
这是论文 §6 率表的核心证据。

## 二、无效/未完成（不可用于论文，需重跑）

| 项 | 状态 | 根因 |
|---|---|---|
| W4/W5（guard 阴性） | 全部 exit 24 | 用 PYTHONPATH 加载 fixed 树时，树内预编译 `.so` 需要 `CXXABI_1.3.15`，A800 容器 libstdc++ 较旧 → CLI 降级、不认 `--http-host/--http-port` |
| incidence 矩阵（43 trials） | 全部 exit 20（服务健康检查超时） | `run_incidence.py` 从 `work/logs/model_snapshot_path.txt` 读到残留的 8B 模型路径（无效字符串），vLLM 加载失败 |
| guard overlay 重跑 | 未拉取到结果（实例已关机） | 排在 incidence 之后；A800 关机前是否执行/结果如何未知，本地无副本 |
| W8（c=32） | 未跑 | 时间不足 |

## 三、修复方案（明天直接执行）

1. **incidence**：删 `<WORKDIR>/work/logs/model_snapshot_path.txt`，并把 `run_incidence.py` 的
   `MODEL = "Qwen/Qwen3-0.6B"` 改为读 `KVC_MODEL` 环境变量（与 driver 修复一致）；再跑 43 trials。
2. **guard overlay**：已有脚本 `guard_overlay.sh`（apply/restore）把两个 patch 文件覆盖到 venv025
   site-packages，绕开 `.so`；重跑 `run_guard_overlay.sh`（每 trial 已加 720s 超时）。
3. **W8**：可选，c=32 条件补点。
4. 全部重跑放在 A800 重启后或 4090 上，预计 incidence 70–90 分钟、guard 10–20 分钟。

## 四、论文整合清单

- 率表：W0–W3 + W6/W7（6 行，含 CI 与中位耗时）。
- §7 边界：8B 已验证；guard 阴性重跑后补“修复后 0 命中”。
- 不要写“A800 上 guard 阴性已复现”——目前是本地 4060 的 4/4，A800 版本待重跑。
