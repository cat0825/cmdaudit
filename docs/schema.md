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
| `canonical` | VARCHAR | 确定性占位符替换的结果，**保留 script 名**。比 `template` 细 |
| `template` | VARCHAR | Drain3 聚类后的命令形状 |
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

## 截断判据

`duration_truncated` 为真的三种情形，任一命中即标记：

1. 输出含仍在运行的标记（`still running`、`Process running with session ID`、
   `SESSION_ID=`）；
2. 耗时 ≥ 29.9 秒且**拿不到退出码**；
3. 上述两者都不满足但有退出码时，一律不标记 —— 有退出码就是真跑完了。

第 2 条的阈值有数据支撑而不是猜的。无退出码的自报耗时分布：

| 耗时区间 | 条数 |
|---|---|
| ≥ 29.9s | 632 |
| 20-29.9s | 69 |
| 10-20s | 846 |
| < 10s | 7935 |

`≥29.9s` 有 632 条而紧邻的 `20-29.9s` 只有 69 条，这个断崖说明 30 秒是工具的
让出上限而非真实耗时分布。有退出码的对照组里 `≥29.9s` 只有 15 条，
进一步确认。

不能用 `result_status = 'completed'` 反证命令跑完了：那个字段说的是
「工具调用完成」，不是「命令退出」。实测 `gh pr checks --watch` 被挂到后台
会话（输出以 `SESSION_ID=` 结尾），工具侧标记 completed 但命令仍在跑。

修正前后对比同一条记录：

```
修正前  npm run test:e2e  total 218.4s  p90 30.0   (含 3 条让出记录)
修正后  npm run test:e2e  total 128.4s  p90 11.07
```

## canonical 与 template 的区别

两者都是「命令形状」，但粒度不同，用途不能互换：

| 列 | 来源 | 粒度 |
|---|---|---|
| `canonical` | 确定性正则替换 | `npm run build` 与 `npm run typecheck` 分开 |
| `template` | Drain3 聚类 | 两者都聚成 `npm run <*>` |

实测差异：`npm run <*>` 这个 Drain3 桶里含 `build`（733 秒 / 153 次）、
`typecheck`（311 秒 / 106 次）、`test:e2e`（490 秒 / 30 次）等。
耗时差好几倍，聚在一起就无法定位该优化哪个 script。

所以候选筛选（`cmdaudit screen`）用 `canonical` 作键，
`template` 只作辅助分桶。

## 复合命令的归因限制

一次工具调用只有一个退出码，但一条命令可以是复合的
（`sleep 5; curl http://x`、`cd /x && npm test`）。
`program` 取的是主程序，所以退出码被归给主程序，
而真正失败的可能是管道后段的另一个程序。

实测影响：`sleep` 有 16 条「失败」，其中多数是 `sleep N; curl ...` 里 curl
连接失败；`head` 的失败里有 `cd` 失败导致的。

这不是 bug 而是数据本身的分辨率上限。使用建议：

- 看 `failure_kind` 与 `error_snippet` 判断真实原因，不要只看 `program`；
- `programs` 列保留了该命令涉及的全部程序，可用于交叉核对；
- 做失败率排名时，把复合命令占比高的程序（`sleep`、`cd`、`head`）
  当成信号弱的项，不要直接当结论。

## 状态取值

| 取值 | 含义 |
|---|---|
| `ok` | 退出码 0，或结果事件为 `completed` |
| `failed` | 退出码非 0（且不属于下面的 `no_match`），或结果事件为 `errored` |
| `no_match` | 「查无结果」：搜索类程序退出码 1（`rg` 无匹配）、比较类退出码 1（`diff` 有差异）、探测类退出码 1（`which` 未安装）。**这是成功的查询得到否定答案，不是失败** |
| `unknown` | 没有任何状态证据。**不代表成功** |

`no_match` 是独立状态的理由：实测 `rg` 有 95 次、`find` 31 次、`which` 20 次
退出码为 1，把它们算失败会让 `rg` 出现在「最容易失败的程序」前列，
而实际上那是它正常工作。判定要求退出码恰好为 1，且输出里没有该程序自己的
错误行（`rg: ...`），后者排除了「用法写错」被误判成查无结果。

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
