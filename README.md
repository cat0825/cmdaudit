# cmdaudit

统计 AI coding agent 会话里**每一条命令执行了什么、花了多长时间、是否失败**，
再交给模型给出「是否必要 / 如何预防」的改进建议。

关注点是**命令级**（`git log`、`npm run build`、`curl`），不是 token 成本，
也不是工具类别（Bash / Read / Edit）。已有工具都停在后两层。

## 为什么不用现成的

| 工具 | 有什么 | 缺什么 |
|---|---|---|
| [agentsview](https://github.com/kenn-io/agentsview) (MIT, 5.1k★) | 20+ agent 的会话解析器、SQLite 归一化库、会话级 timing | `tool_calls` 无 `duration_ms`/`exit_code`；58k 条 Bash 塌成一个 category |
| [ccusage](https://github.com/ccusage/ccusage) (18k★) | token / 成本统计 | 不看命令 |
| [claude-code-otel](https://github.com/ColeMurray/claude-code-otel) (487★) | 官方 OTel `tool_result` 事件带 `duration_ms` | 只有 `name`/`success`，**无命令内容**；且只能前向采集，历史会话拿不到 |
| [atuin](https://github.com/atuinsh/atuin) (31k★) / [cmd-wrapped](https://github.com/YiNNx/cmd-wrapped) (1.3k★) | shell 历史的耗时与退出码统计 | 只覆盖人手敲的命令，agent 在子进程里跑的命令不进 shell history |

命令级审计这一层，GitHub 上目前是空白。

## 架构

```
agentsview sessions.db ─┐
（只读）                 ├─→ cmdaudit extract ─→ commands 表 ─→ report / screen
原始 JSONL (兜底) ──────┘      归一化+分类         DuckDB
```

主输入是 agentsview 的 `~/.agentsview/sessions.db`，白嫖它 20+ agent 的解析器。
它没落库的 `duration_ms` / `exit_code`，从 `result_content` 里补解析
（Codex 自报 `Wall time: X seconds` 和 `Process exited with code N`，
本机实测 44915 / 26706 条命中）。

## 复用清单

- **agentsview** — 会话发现与解析（MIT，作为数据源，不 fork）
- **tree-sitter-bash** (MIT) — 命令拆解，替代 GPL-3.0 的 bashlex
- **Drain3** (IBM, MIT) — 命令模板自动聚类，替代手写正则
- **DuckDB** (MIT) — 聚合查询

## 证据等级

工具输出分两级，不混用：

| 输出 | 等级 | 用法 |
|---|---|---|
| `report.md` / `summary.json` | 客观事实 | 命令原文、耗时、退出码，可直接引用 |
| `candidates.json` | `exploratory` | 待验证假设，**不得计入质量声明** |

cmdaudit **不判定**「某条命令是否必要」—— 那个问题只能由
「删掉它之后故障是否漏掉」来回答，需要反事实实验。
工具的职责是把几万条命令压缩到值得做实验的几百条，降低搜索成本，
而不是替代验证。详见 [`docs/plan.md`](docs/plan.md) §5.1。

## 快速开始

需要 Python 3.12+ 和已有的 `~/.agentsview/sessions.db`。

```bash
pip install -e .
cmdaudit extract              # 只读源库，抽取命令到 ./out/
cmdaudit report               # 生成 report.md + summary.json
cmdaudit screen               # 筛出待验证候选（假设，非结论）
cmdaudit viz                  # 生成 report.html（离线单文件，可下钻到命令原文）
```

本机实测：58898 条 Bash tool_call → 53341 条命令，耗时 90 秒。
表结构与每列的取值来源见 [`docs/schema.md`](docs/schema.md)。

读数前先看 `duration_source` 列：`self_reported` 是进程自报的精确墙钟，
`turn_delta` 含模型思考时间只是上界，`batch_shared` 是并发批次共享值
**不能进分位数统计**。

```bash
# 例：按分组统计耗时，排除不可信的耗时来源
duckdb out/commands.duckdb -c "
  SELECT command_group, count(*) n, round(sum(duration_s)) total_s
  FROM commands
  WHERE duration_source IN ('self_reported', 'turn_delta')
  GROUP BY 1 ORDER BY 3 DESC;"
```

## 报告怎么读

耗时与失败是两套证据，覆盖范围不同，**不要跨表相加**。

原因是本机数据里 `self_reported`（进程自报墙钟）100% 来自 codex，
非 codex 的 14345 条命令只有 7 条有自报耗时。所以：

- **失败分析**不依赖耗时，覆盖全部 9 个 agent，是主线。
- **耗时分析**只在自报墙钟上成立，结论不可外推到其他 agent。

每张表都打印自己的口径与可复现的 SQL。三类记录被排除在耗时统计外：
`batch_shared`（批次共享总墙钟）、`unknown`（无证据）、
`duration_truncated`（命令未跑完就被工具让出）。

## 可视化怎么读

`cmdaudit viz` 生成 `out/report.html`：单文件、离线、双击即开，无 CDN 与埋点。

它不是监控大屏，是一次性历史审计的下钻工具。页面按证据轨道分区
（失败线 / 耗时线 / 候选队列），每条轨道自带口径与 caveat；
点开任意聚合行可看该行的命令原文样本与可复现 SQL。
数字与 `report.md` 同源同 SQL，两份产物不会给出不同结论。

```bash
cmdaudit viz --out-dir out --open
```

## 状态

M1（抽取与归一化）、M2（聚合与报告）、M3（候选筛选）、M5（可视化）已完成。
计划见 [`docs/plan.md`](docs/plan.md)，调研记录见 [`docs/research.md`](docs/research.md)。

### M1 实测结果

| 项 | 值 |
|---|---|
| 源库 Bash tool_call | 58898 |
| 排除（`write_stdin` / `apply_patch` 等非命令） | 3766 |
| 排除（`input_json` 无命令键） | 4935 |
| 落库命令 | 53341 |
| tree-sitter 解析降级 | 190（0.36%） |
| 全量抽取耗时 | 92 秒 |

耗时证据分级：`self_reported` 65.7%、`turn_delta` 27.4%、
`batch_shared` 6.4%、`unknown` 0.4%。

### M2 实测结果

| 项 | 值 |
|---|---|
| 可用于耗时统计 | 46959 |
| 判定为失败 | 2007 |
| 查无结果（非失败） | 254 |
| 耗时被工具让出截断 | 3016 |
| 报告表数量 | 8 |

M2 期间修掉两个 M1 的语义缺陷：

- **工具让出截断**。612 条自报耗时聚集在 30.0-30.5 秒，那是 `yield_time_ms`
  的让出上限而非命令耗时，其中 473 条没有退出码。新增 `duration_truncated`
  标记并排除出耗时统计。
- **`no_match` 不是失败**。`rg` / `find` 退出码 1 是查无结果，
  `which` 的 1 是未安装。修正前 `rg` 以 133 次失败排在前列，实际只有 38 次真失败。

### M3 实测结果

四条确定性规则产出 42 条候选：`wait_polling` 13、`duration_hotspots` 12、
`repeated_failures` 10、`timeout_and_network_clusters` 7。

契约在**构造时**强制，不是事后检查：`evidence_class` 非 `exploratory`、
`status` 非 `unverified`、判决式措辞（「不必要」「应删除」「redundant」）、
假设缺少限定词、观测依据为空，五类越界都会抛 `ContractViolation`。
