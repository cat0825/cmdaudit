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
                        ├─→ cmdaudit extract ─→ commands 表 ─→ report / analyze
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

## 状态

设计阶段。计划见 [`docs/plan.md`](docs/plan.md)，调研记录见 [`docs/research.md`](docs/research.md)。
