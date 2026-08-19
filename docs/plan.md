# 实施计划

目标：回答四个问题 —— 我的 agent 都跑了什么命令、各花多长时间、
哪些失败了、哪些不必要或可预防。

原则：能复用就不自研（见 [`research.md`](research.md)）。
主输入是 agentsview 的 SQLite，自研部分只做它缺的命令级那一层。

## 数据流

```
~/.agentsview/sessions.db  (只读, agentsview 20+ agent 解析器)
        │
        │  extract：补 duration_ms / exit_code / status
        │           tree-sitter-bash 拆程序，Drain3 聚模板
        ▼
   commands 表 (DuckDB)
        │
        ├─→ report：按 program / template / group 聚合，Markdown + JSON
        └─→ analyze：喂模型，产出必要性判定与预防措施
```

原始 JSONL 作兜底解析器，只在 agentsview 没覆盖某 agent 时启用。

## M1 抽取与归一化

**目标**：`cmdaudit extract` 跑通，产出带耗时与状态的 `commands` 表。

`commands` 表核心列：

| 列 | 说明 |
|---|---|
| `session_id` `agent` `started_at` `cwd` | 来源标识 |
| `command` | 原始命令 |
| `duration_ms` | 耗时 |
| `duration_source` | `self_reported` / `turn_delta` / `batch_shared` / `unknown` |
| `exit_code` | 退出码，无则 NULL |
| `status` | `ok` / `failed` / `timeout` / `interrupted` / `unknown` |
| `program` `subcommand` | 主程序与子命令，tree-sitter 提取 |
| `command_group` | vcs / build / test / net / pkg / search / fs / lint / other |
| `template` `template_id` | Drain3 聚类结果 |
| `failure_kind` | timeout / network / not_found / permission / build / test / other |

**耗时取值优先级**，高位缺失才降级，且必须记录 `duration_source`：

1. `self_reported` — 进程自报，解析 `result_content` 里的 `Wall time: X seconds`
2. `turn_delta` — 相邻 message 时间戳差值（agentsview `timing.go` 的算法）
3. `batch_shared` — 并行批次共享一个总墙钟，聚合时单独处理，不参与 p50/p90
4. `unknown` — 都拿不到

**状态判定优先级**，这条顺序是原型踩坑换来的：

1. 有 `exit_code` → 直接用。**`exit_code == 0` 时不再看输出文本**
2. 有 `tool_result_events.status` → 用
3. 都没有 → 文本启发式，且只扫 stderr，扫全量输出会把 grep 到的
   `error:` 当成失败（原型里这让报错率虚高 4.7 个百分点）

**验收**：
- 本机 79516 条 tool_call 全量跑通，`duration_source` 各档位占比打印出来
- `exit_code=0 AND status='failed'` 必须为 0 条
- 单元测试覆盖三种耗时降级路径和四种状态判定路径
- 各 agent 至少一个真实 fixture（脱敏），codex 新旧两种格式都要有

## M2 聚合与报告

**目标**：`cmdaudit report` 输出可直接读的统计。

维度：program / template / command_group / agent / project。
指标：count、total_ms、p50、p90、max、error_rate、timeout_rate、耗时占比。

排序默认按 `total_ms` 降序 —— 「哪条命令吃掉我最多时间」是第一诉求。

三张专项表：
- **耗时榜**：按 template 聚合的总耗时 top 30
- **失败榜**：按 `failure_kind` 分组，附错误片段样本
- **超时榜**：`failure_kind IN ('timeout','network')` 单列，这是你最初的诉求

`batch_shared` 的记录在分位数统计里排除，只计入总量并标注，
否则 p90 会被均摊值污染。

**验收**：报告里每个数字可由一条 SQL 复现，文档附查询。

## M3 模型分析

**目标**：`cmdaudit analyze` 产出改进建议。

输入是 M2 的聚合结果 + 每个高开销模板的若干真实样本（含错误片段），
不是全量命令 —— 79516 条塞不进上下文，也没必要。

要求模型按四段输出：

1. **必要性判定**：必要 / 可合并 / 可缓存 / 可删除，附依据
2. **耗时归因**：网络 / 磁盘 IO / 编译 / 等待进程 / 超时重试 / 参数误用
3. **预防措施**：能直接落进 `AGENTS.md`、脚本或 alias 的规则，给命令示例
4. **优先级**：按「节省时间 × 出现频率」排序取前 10

默认走本地已装的 agent CLI（复用 agentsview insights 的思路，
数据不出本机）。

**验收**：至少一条建议可落地并复测出耗时下降。

## M4 可选增强

按需再做，不阻塞前三步：

- **反哺 agentsview**：M1 的归一化列若稳定，向上游提 PR
  （`tool_calls` 加列走 `migrateColumns()`，bump `dataVersion`；
  注意 PG 与 DuckDB 镜像 schema 要同步，否则 `pg push` 静默丢字段）
- **重试链检测**：同 template 在窗口内重复且前次失败 → 标 `retry_of`
- **OTel 接入**：作为 Claude Code 侧的精确耗时补充
- **趋势对比**：两个时间窗口的 diff，验证改进是否真的生效

## 风险

| 风险 | 应对 |
|---|---|
| Claude 侧无自报耗时，并行调用拿不到单条耗时 | `duration_source` 显式标记，UI 与报告区分精确值与推断值，不混用 |
| agentsview schema 变动（`dataVersion` 已到 59） | 只读固定几列，启动时校验 schema，不匹配就报错而非静默出错数 |
| 命令含密钥（`curl -H "Authorization: ..."`） | 落库前脱敏，模板化天然去掉字面量；导出与分析前再过一遍 |
| 1.6 GB 库全量扫描慢 | 增量抽取，按 `session_id` 做 watermark |
| agent 间 `input_json` 键名不一致 | 至少覆盖 `command` / `cmd` / `CommandLine` 三种（agentsview 前端 `tool-summary.ts:121` 已有先例） |

## 不做什么

- 不做 token / 成本统计，ccusage 已经做透
- 不做会话浏览 UI，agentsview 已经做透
- 不 fork agentsview
- 不做实时监控，这是离线审计工具
