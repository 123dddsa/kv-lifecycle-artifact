# kvc-lifecycle 0.8.0 工具评估（task-3）

日期：2026-11-17（Asia/Shanghai）
主机：Windows 11 (10.0.26200)，Intel i7-13650HX 14C/20T，CPython 3.14.7，pytest 9.2.0，**无 Docker**。
所有数字来自 `raw/` 下的原始日志与 JSONL；命令见 `scripts/`，可重放。原始素材由 task-3 产生，本文件由 Lead 在子代理中断后据原始数据汇总（未重跑）。

## 1. 安装成本（全新 venv，pip install -e ".[dev]"）

| run | venv 创建 (s) | pip install (s) | 备注 |
|---|---:|---:|---|
| 1 | 13.58 | 27.12 | warm pip cache |
| 2 | 10.31 | 21.21 | warm |
| 3 | 10.00 | 21.29 | warm |
| 4 | 10.12 | 26.58 | **cold**（`PIP_NO_CACHE_DIR` 类冷启动） |

- venv 创建中位 **10.1 s**；`pip install -e ".[dev]"` 中位 **≈23.9 s**（4 次：21.21/21.29/26.58/27.12）。
- 无 runtime 依赖（仅 dev extra 装 pytest），4/4 次 `pip_exit=0`。
- 数据：`raw/install_runs.jsonl`、`raw/install_run*.log`。

## 2. 测试套件

| run | wall (s) | 结果 |
|---|---:|---|
| 1 | 6.63 | 68 passed + 7 subtests |
| 2 | 5.36 | 68 passed + 7 subtests |
| 3 | 5.63 | 同上 |

pytest 自报耗时 4.37–4.45 s；`raw/pytest_runs.jsonl`、`raw/pytest_run*.log`。另有 `unittest_run1.log`（unittest 路径同样全绿）。

## 3. CLI 冒烟（真实输出见 `raw/cli_smoke.log`）

| 命令 | 结果 | exit |
|---|---|---:|
| `kvc version` | `0.8.0` | 0 |
| `kvc codes` | 列出 8 个 violation code | 0 |
| `check examples/normal_recv.jsonl` | 0 violations / PASS | 0 |
| `check examples/vllm_0251_stale_send.jsonl` | `I_COMPLETION_AFTER_FREE`（step=2，free at step 1）/ FAIL | **1** |
| `check ... --format json` | `event_count: 5`、`violation_count: 1`、`step: 2` | 1 |
| `check examples/stale_send.jsonl` | 1 violation / FAIL | 1 |
| `check examples/scoped_children.jsonl --identity-scope request` | FAIL（裸 ID 重复） | 1 |
| 同文件 `--identity-scope child_request_attempt` | PASS（scoped 身份） | 0 |
| `audit` / `aggregate` / `cost` | 见 `raw/cli_smoke.log` 后续段 | 见日志 |

## 4. monitor 开销（复刻 `<LOCAL_WORKSPACE>/benchmark_contract.py::monitor_only` 口径）

| 实现 | μs/action（5 个 trace 规模 × 3 独立 run，见 `raw/monitor_bench_compare.json`） |
|---|---|
| 新 scoped monitor 0.8.0 | **1.15–1.67**（5 个规模 × 3 run 的样本 1.1455–1.6711；规模中位 1.254–1.6075） |
| 旧 legacy contract（`repro_scripts/contract.py`） | **0.45–0.72**（样本 0.4466–0.7230；规模中位 0.4654–0.5754） |
| no-op 基线（同循环空实现） | 0.07–0.11（样本 0.0714–0.1053） |

说明：v3 稿中的 0.43–0.51 μs/action 是**旧 legacy monitor + WSL2** 的数字；0.8.0 用了 scoped 身份字典，故在同机复测为 1.15–1.67 μs/action（legacy 同机 0.45–0.72）。论文按新数字写，并注明旧值来源差异。该口径是“每 action 的 monitor 处理成本”，不含 adapter/真实组件开销。

## 5. 接入/规模/工程事实（`raw/access_cost.json`）

- `src`：14 个 Python 文件，2,141 行，SLOC **1,837**（非空非注释），AST statements 1,054。
- adapter `vllm_lmcache.py`：119 行（SLOC 103）。
- monitor：`core/monitor.py`（见 access_cost.json 的 monitor 段）。
- CLI：492 行（SLOC 447）。
- pytest 插件、CI workflow、Dockerfile：见 `access_cost.json` 的 `pytest_plugin` / `ci_workflow` / `dockerfile` 段（Dockerfile 存在，**本机无 docker，未 build**）。
- 工具树完整性：43/43 文件，SHA-256 与交接包一致（`raw/tool_tree_integrity.json`）。

## 6. 匿名 artifact

- 打包脚本运行成功（`raw/artifact_package.log`）；产出的 zip：**42 payload 文件 + manifest**，45,232 B，sha256 `59622f30…`。
- manifest 全部相对路径，42 条 entry 与 zip payload 一一匹配。
- 泄漏扫描：**0 命中**（`leak_hits: []`）；仅在 `scripts/package_artifact.py` 内出现扫描用的 `<HOME>/`、`<HOME> 字符串（预期自标记，非泄漏）。
- artifact 与交接包 tool 树 42/42 文件哈希一致（`raw/artifact_vs_handoff_manifest.json`）。

## 7. Quickstart（干净环境）

| run | venv 创建 | 安装 | `kvc check` | 端到端 |
|---|---:|---:|---:|---:|
| 1 | 11.12 s | 21.18 s | 0.42 s | **32.74 s** |
| 2 | 9.39 s | 20.48 s | 0.47 s | **30.34 s** |

中位端到端 **≈31.5 s**（从建 venv 到 `check` 输出 PASS）。数据：`raw/quickstart_runs.jsonl`。

## 8. 边界

- 单机、单核时环境；无开发者可用性研究。
- Dockerfile 未 build（主机无容器运行时）。
- CI 矩阵本地跑通（同 pytest/unittest/CLI 三类命令），未在托管 runner 执行。
- monitor 数字是微基准，不是生产吞吐；论文不写在线开销主张。

