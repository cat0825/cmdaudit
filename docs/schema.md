# commands 表

`cmdaudit extract` 的落库结果，位于 `<out-dir>/commands.duckdb`。
每行是一条被 agent 执行过的 shell 命令。

主键 `(call_id, slot)`：一个 tool_call 可能承载多条命令
（Codex 旧格式的 JS 脚本会在一次调用里跑多条），`slot` 是它在该调用里的序号。

## 列

| 列 | 类型 | 取值来源 |
|---|---|---|
| `session_id` | VARCHAR | `tool_calls.session_id` |
| `agent` | VARCHAR | `sessions.agent`，例如 `codex` / `claude` / `antigravity` |
| `project` | VARCHAR | `sessions.project` |
| `call_id` | BIGINT | `tool_calls.id` |
| `slot` | INTEGER | 该命令在这次 tool_call 里的序号，从 0 起 |
| `started_at` | VARCHAR | 所属 message 的 `timestamp`（UTC ISO8601） |
| `tool_name` | VARCHAR | `tool_calls.tool_name` |
| `command` | VARCHAR | 命令原文，**已脱敏** |
| `workdir` | VARCHAR | `input_json` 里的 `workdir` / `cwd`，可能为空 |
| `input_kind` | VARCHAR | 命令是从哪个键抽出的：`cmd` / `command` / `CommandLine` / `js_script` |
| `duration_s` | DOUBLE | 见下方「耗时分级」 |
| `duration_source` | VARCHAR | 耗时的证据等级，**读数前必须先看这一列** |
| `exit_code` | BIGINT | 从输出里解析；用 BIGINT 因为 Windows 会给出 `0xC0000409` 这类值 |
| `status` | VARCHAR | `ok` / `failed` / `unknown` |
| `status_source` | VARCHAR | 状态是怎么定的：`exit_code` / `result_event` / `text_heuristic` / `none` |
| `failure_kind` | VARCHAR | 仅 `failed` 时非空，见下方「失败归因」 |
| `error_snippet` | VARCHAR | 错误片段，供人工核对；最长 400 字符 |
| `program` | VARCHAR | 主程序，tree-sitter-bash 解析 |
| `programs` | VARCHAR | 该命令涉及的全部程序，逗号分隔 |
| `subcommand` | VARCHAR | 仅对 `git` / `npm` / `gh` 这类带子命令的程序非空 |
| `command_group` | VARCHAR | 手维护的分组表，见下方 |
| `parse_ok` | BOOLEAN | tree-sitter 是否无错解析；`false` 表示 `program` 来自降级路径 |
| `template` | VARCHAR | 字面量替换成占位符后的命令形状 |
| `template_id` | VARCHAR | `blake2b(program + subcommand + template)` 短哈希 |
| `redacted` | BOOLEAN | 该命令是否发生过脱敏替换 |

## 耗时分级

`duration_source` 是必读列。把推断值当精确值用会得出错误结论。

| 取值 | 含义 | 能否进分位数统计 |
|---|---|---|
| `self_reported` | 进程自报的墙钟，最可信 | 可以 |
| `turn_delta` | 相邻 message 时间戳差值。**含模型思考时间**，是命令耗时的上界 | 可以，但要标注 |
| `batch_shared` | 并发批次共享的总墙钟，同批多条命令值相同 | **不可以** |
| `unknown` | 拿不到任何耗时证据，`duration_s` 为 NULL | 不可以 |

两条硬规则：

- `batch_shared` 的值是批次总墙钟，**不是**均摊值。均摊会让每条数据都是错的，
  所以聚合时必须按 `duration_source` 过滤，而不是直接 `sum(duration_s)`。
- `turn_delta` 超过 300 秒的差值一律降级为 `unknown`。实测最大差值 39087 秒
  （约 10.9 小时），那是会话空闲不是命令耗时；自报耗时的 p99 只有 30 秒。

## 状态判定

优先级从高到低，高位命中即停：

1. `exit_code` —— **退出码为 0 时直接判 `ok`，绝不再看输出文本**。
   这条是红线：读日志时输出里出现 `error:` 会让报错率虚高约 5 个百分点。
2. `tool_result_events.status` —— `completed` / `errored`。
3. 文本启发式 —— 只在前两级都无证据时使用。

`status = unknown` 表示没有任何状态证据，**不代表成功**，统计时要单独计。

## 失败归因

`failure_kind` 由规则判定，不用模型：

`timeout` / `network` / `not_found` / `permission` / `build` / `test` /
`interrupted` / `other`

## 命令分组

`wait` / `vcs` / `build` / `test` / `pkg` / `net` / `search_read` /
`fs_mutate` / `lint_fmt` / `runtime` / `container` / `db` / `proc_sys` /
`shell_noop` / `other`

`wait` 是独立分组，不并入 `proc_sys`：等待外部系统既不是有效工作也不是进程管理，
混在一起会掩盖信号。

## 被排除的记录

`extract_stats` 表与 `extract-stats.json` 记录每一类排除的条数，
报告里要能解释所有去向：

| key | 含义 |
|---|---|
| `bash_tool_calls` | 源库 `category='Bash'` 的总行数 |
| `excluded_tool` | `write_stdin` / `apply_patch` 等不承载命令的工具 |
| `no_command_key` | `input_json` 里没有任何命令键 |
| `commands_written` | 实际落库条数 |
| `parse_failed` | tree-sitter 解析失败、走降级路径的条数 |
| `redacted` | 发生过脱敏替换的条数 |
