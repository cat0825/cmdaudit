# 调研记录

调研日期 2026-08-19。所有数字来自本机实测，命令附在各节末尾。

## 1. 结论

命令级审计（每条命令的耗时、退出码、必要性）在 GitHub 上是空白。
相邻生态分三类，都不覆盖这一层：

- **token / 成本类**（ccusage 18k★ 及十余个衍生 dashboard）：只统计 token 与费用。
- **会话浏览类**（agentsview 5.1k★）：有完整的多 agent 解析器和会话级 timing，
  但命令维度塌成 category。
- **shell 历史类**（atuin 31k★、cmd-wrapped 1.3k★）：有精确耗时与退出码，
  但只覆盖人在终端敲的命令。

因此策略是：**复用 agentsview 的解析层，自研命令级的抽取、归一化、聚合、分析。**

## 2. 候选逐个评估

### agentsview — 主数据源，复用

MIT / 5132★ / 2026-08-19 仍在推送 / Go 855 文件。本机已装并跑着 daemon。

已有且值得复用：

- 20+ agent 的会话解析器（`internal/parser/`，实测本机库里有 codex、claude、
  antigravity、opencode、pi、omp、hermes、cowork 等 8 个 agent 的数据）
- 归一化好的 SQLite：`sessions` / `messages` / `tool_calls` / `tool_result_events`
- 会话级 timing 计算（`internal/db/timing.go`），含 category 归因

缺口（实测）：

| 缺口 | 证据 |
|---|---|
| `tool_calls` 无 `duration_ms` / `exit_code` / `status` | `PRAGMA table_info(tool_calls)` 只有 13 列，无一个是时间或状态 |
| 耗时是查询时现算，跨会话聚合不了 | `internal/db/timing.go:104-120` 从 `messages.timestamp` 算 `delta_ms` |
| 并行调用耗时判 NULL | `timing.go:293-299` 注释自认；实测 17789/79516（22%）受影响 |
| Codex 自报的墙钟被丢弃 | `result_content` 里 44915 条含 `Wall time`、26706 条含 `Process exited with code`，但 `rg 'Wall time' --type go` 零命中 |
| 无命令维度 | `GetAnalyticsTools`（`internal/db/analytics.go:2850`）只按 category + agent 聚合，58287 条 Bash 是一个桶 |
| 失败判定只到会话级 | `internal/signals/toolhealth.go:49` 产出 4 个标量，问不出「哪条命令最常失败」 |

结论：**不 fork**。fork 一个 855 文件、每天在推送的 Go 项目，维护成本远超收益。
改为消费它的 `~/.agentsview/sessions.db`（只读），把它当解析层白嫖。
上游若接受，P1 的归一化列可以反向提 PR。

### Claude Code 官方 OTel — 不够用

`claude_code.tool_result` 事件确实带 `duration_ms` 和 `success`
（见 claude-code-otel 的 `CLAUDE_OBSERVABILITY.md:229-240`）。两个硬伤：

1. 属性只有 `name` / `success` / `duration_ms` / `error`，**没有命令内容**。
   知道「某次 Bash 花了 23s」但不知道那是 `npm install` 还是 `git log`，
   对「这条命令是否必要」毫无帮助。
2. 只能前向采集。历史会话（本机 294 个 Claude JSONL + 184 个 Codex rollout）拿不到。

可作为后续可选的精确数据源，不作为主路径。

### atuin / cmd-wrapped — 思路可借，数据不可用

atuin 记录 `duration` 和 `exit`，cmd-wrapped 做 shell 历史统计，
两者的指标设计（p50/p90、按程序聚合）值得照抄。
但 agent 在子进程里跑的命令**不进 shell history**，数据源对不上。

### ccusage 系 — 无关

只做 token 与成本，不解析命令。

## 3. 库选型

| 需求 | 选择 | 许可 | 否决的替代 |
|---|---|---|---|
| 拆解 shell 命令、提取主程序 | **tree-sitter-bash** 0.25.1 | MIT | `bashlex` 是 **GPL-3.0**，会传染；`shlex` 遇到 `&&`/重定向/heredoc 就废 |
| 命令模板聚类 | **Drain3** 0.9.11 (IBM) | MIT | 手写正则，规则会无限膨胀 |
| 聚合查询 | **DuckDB** 1.1.3 | MIT | pandas 够用但 SQL 表达聚合更省代码 |

两个库都实测过。

tree-sitter-bash 对复合命令解析正确：

```python
src = b'''cd /x && git log --oneline | head -3; VAR=1 npm run build 2>&1 || echo fail
for f in *.py; do python3 $f; done'''
# → programs: ['cd', 'git', 'head', 'npm', 'echo', 'python3']
# → has_error: False
```

Drain3 能把同族命令自动归一：

```
git log --oneline -12   → cluster 1: git log --oneline <*>
git log --oneline -30   → cluster 1
rg -n foo src/a.py      → cluster 2: rg -n <*> <*>
rg -n bar src/b.py      → cluster 2
npm run build           → cluster 3
```

注意 Drain3 的 `<*>` 只做位置级替换，语义分组仍需 tree-sitter 给出的
主程序 + 子命令作为分桶键，两者是互补而非替代关系。

## 4. 原型验证

先用 `~/.codex/scripts/workflows/agent_cmd_audit.py`（纯标准库，715 行）验证了可行性：
直接读 Claude / Codex 的 JSONL，解析出 479 文件 / 12776 条记录 / 3836 条 shell 命令。

暴露的两个坑，正式实现必须处理：

1. **纯文本判失败会误判**。初版报错率 20.3%，加入「exit code 为 0 时不信文本」
   的判定后降到 15.6%。误判来源是 `grep`/日志读取的输出里出现 `error:`。
2. **并行批次的耗时不能均摊**。Codex 旧格式一个 JS 脚本里 `Promise.all` 并发多条
   `exec_command`，只有外层一个总墙钟。均摊会让每条命令的耗时都是错的，
   必须显式标记 `duration_source=batch_shared` 并在聚合时单独处理。
3. **两个正则陷阱**，原型都踩了：
   - 实际格式是 `Wall time 1.2 seconds`，**没有冒号**。写成
     `Wall time:?\s*([0-9.]+)\s*seconds` 后对 43336 条命中率 100%。
   - 内层 JSON 是**转义**的：`\"wall_time_seconds\":1.002`。原型的正则
     要求未转义引号，导致 1295 个并发脚本全部降级；修正为
     `wall_time_seconds[\\"]*\s*:\s*([0-9.]+)` 后，**365 个脚本可救回
     逐条精确耗时**。
4. **`Bash` category 里 25% 不是命令**。实测 14838/58287 条的 `input_json`
   没有任何命令键，其中 `write_stdin` 3748 条只是向已有进程轮询
   （`{session_id, yield_time_ms, max_output_tokens}`），`apply_patch` 1468 条
   是打补丁。不排除会给统计灌 6% 的水。

## 5. 数据规模

| 数据源 | 规模 |
|---|---|
| `~/.agentsview/sessions.db` | 1.6 GB，1600 会话 / 111 项目，`tool_calls` 79516 行，其中 Bash 58287 行（可抽取命令约 51857 条） |
| `~/.claude/projects/**/*.jsonl` | 294 文件 / 143 MB |
| `~/.codex/sessions` + `archived_sessions` | 184 文件 / 250 MB |

Bash 命令的 agent 分布：codex 43764、antigravity 4843、opencode 3555、pi 3062、
omp 1661、claude 1367、hermes 60、cowork 4。

`Wall time` 的 agent 分布很不均：codex 44910、pi 8、claude 1。
**Claude Code 侧没有自报耗时，只能靠时间戳差值，并行调用拿不到单条耗时。**
这是 `duration_source` 列必须存在的原因。

## 6. 复现命令

```bash
# agentsview schema 与规模
sqlite3 -readonly ~/.agentsview/sessions.db "PRAGMA table_info(tool_calls);"
sqlite3 -readonly ~/.agentsview/sessions.db \
  "SELECT category, count(*) FROM tool_calls GROUP BY category ORDER BY 2 DESC;"

# 自报耗时 / 退出码的覆盖率
sqlite3 -readonly ~/.agentsview/sessions.db \
  "SELECT count(*) FROM tool_calls WHERE result_content LIKE '%Wall time%';"
sqlite3 -readonly ~/.agentsview/sessions.db \
  "SELECT count(*) FROM tool_calls WHERE result_content LIKE '%Process exited with code%';"

# 并行调用占比
sqlite3 -readonly ~/.agentsview/sessions.db "
  SELECT c>=2 AS is_parallel, count(*) FROM
    (SELECT message_id, count(*) c FROM tool_calls GROUP BY message_id) p
    JOIN tool_calls USING(message_id) GROUP BY is_parallel;"

# agentsview 的缺口
rg -n 'Wall time|exit_code' --type go ~/Documents/GitHub/agentsview/internal   # 零命中
```
