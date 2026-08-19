# 实施计划

目标：回答四个问题 —— 我的 agent 都跑了什么命令、各花多长时间、
哪些失败了、哪些不必要或可预防。

本文档约束**实现方式**、**实现内容**、**停止条件**。
调研与选型依据见 [`research.md`](research.md)。

---

## 0. 范围边界

### 做

命令级审计：从已有会话记录里抽取每条 shell 命令，附耗时、退出码、失败归因，
聚合成统计，再交给模型给出改进建议。离线、只读、本机。

### 不做

- token / 成本统计 —— ccusage 已做透
- 会话浏览 UI —— agentsview 已做透
- fork agentsview —— 855 个 Go 文件且每天推送，维护成本远超收益
- 实时监控 / 常驻进程 —— 这是离线审计工具
- 自动执行改进建议 —— 只输出建议，改不改由人决定

### 硬约束

| 约束 | 理由 |
|---|---|
| 对 `~/.agentsview/sessions.db` **只读**（`mode=ro`） | 那是 agentsview 的生产库，1.6 GB，且有 daemon 在写 |
| 不碰 agentsview 的 daemon、配置、进程 | 同上 |
| 全部输出写到 `./out/` 或 `--out-dir` 指定目录 | 不污染用户目录 |
| 落库前脱敏 | 命令里可能有 `curl -H "Authorization: ..."` |
| 依赖只允许 4 个：`tree-sitter-bash`、`tree-sitter`、`drain3`、`duckdb` | 都是 MIT；每加一个依赖需在 PR 里说明理由 |
| 不引入 GPL 代码 | `bashlex` 因此被否决 |

---

## 1. 技术栈与项目结构

Python 3.12+（本机 3.12.2）。选 Python 不选 Go 的理由：Drain3 和
tree-sitter 的 Python 绑定成熟，且这是离线分析工具，不需要 Go 的部署优势。

```
cmdaudit/
├── src/cmdaudit/
│   ├── __init__.py
│   ├── cli.py              # argparse 入口：extract / report / analyze
│   ├── sources/
│   │   ├── agentsview.py   # 主数据源：只读 SQLite
│   │   └── jsonl.py        # 兜底：直读 Claude/Codex JSONL（M4）
│   ├── extract/
│   │   ├── command.py      # input_json → 命令原文（多键名 + JS 脚本）
│   │   ├── duration.py     # 耗时四级降级
│   │   ├── status.py       # 状态判定 + failure_kind
│   │   └── shellparse.py   # tree-sitter-bash 封装
│   ├── normalize/
│   │   ├── template.py     # Drain3 封装
│   │   ├── group.py        # command_group 分类表
│   │   └── redact.py       # 脱敏
│   ├── store.py            # DuckDB schema + 写入
│   ├── report.py           # 聚合查询 + Markdown/JSON 渲染
│   └── analyze.py          # 模型分析
├── tests/
│   ├── fixtures/           # 各 agent 脱敏样本
│   └── test_*.py
├── docs/
├── pyproject.toml
└── README.md
```

风格约束：类型标注齐全，`ruff` + `mypy` 干净，纯函数优先
（解析层不碰 IO，方便测试）。

---

## 2. 数据流

```
~/.agentsview/sessions.db  (只读)
        │
        ├─ extract ─→ commands 表 (DuckDB)
        │             命令原文 / 耗时 / 状态 / 程序 / 模板 / 分组
        │
        ├─ report ──→ report.md + summary.json
        │
        └─ analyze ─→ analysis.md
```

---

## 3. M1 抽取与归一化

### 3.1 命令抽取

`tool_calls.category='Bash'` 有 58287 行，但**不都是命令**。实测键名分布：

| 键名 | 条数 | 处理 |
|---|---|---|
| `cmd` | 28583 | 直接取 |
| `command` | 10488 | 直接取 |
| `CommandLine` | 4646 | 直接取 |
| 无以上键 | 14838 | 需分辨 |

无键的 14838 条里，`tool_name` 分布为：`exec` 10882、`write_stdin` 3748、
其他 12。其中：

- **`exec` 10882 条**是 Codex 旧格式，命令内嵌在 JS 脚本里
  （`tools.exec_command({cmd:"..."})`）。7488 条含 `exec_command`，
  1468 条是 `apply_patch`，其余是 MCP 调用等。必须单独解析。
- **`write_stdin` 3748 条**是向已有进程轮询，`input_json` 只有
  `{session_id, yield_time_ms, max_output_tokens}`，**不是命令**，必须排除。
  不排除会给统计灌 6% 的水。

JS 脚本里的 `cmd:` 提取不能用正则一把梭 —— 字符串可能是 `"`、`'`、
反引号三种引号，且含转义。用手写的引号感知扫描器（原型已验证），
不上 JS parser（为提一个字段引入 JS 运行时不划算）。

**验收**：抽取出 51857 ± 200 条命令。`write_stdin` 与 `apply_patch` 零混入。

### 3.2 耗时四级降级

每条命令必须落 `duration_source`，**不允许把推断值当精确值**。

| 级别 | 来源 | 实测占比 |
|---|---|---|
| `self_reported` | 进程自报的墙钟 | 33952 (65.5%) |
| `turn_delta` | 相邻 message 时间戳差值 | 14864 (28.7%) |
| `batch_shared` | 并发批次共享总墙钟 | 3041 (5.9%) |
| `unknown` | 都拿不到 | 0 |

两个解析陷阱，都是实测踩出来的：

1. **格式是 `Wall time 1.2 seconds`，没有冒号。**
   正则必须写成 `Wall time:?\s*([0-9.]+)\s*seconds`，实测对 43336 条
   命中率 100%。
2. **内层 JSON 是转义的。** `result_content` 里嵌的是
   `\"wall_time_seconds\":1.002` 而非 `"wall_time_seconds":1.002`。
   正则必须写成 `wall_time_seconds[\\"]*\s*:\s*([0-9.]+)`。
   原型漏了这点，导致 1295 个并发脚本全部降级成 `batch_shared`；
   修正后 **365 个脚本可救回逐条精确耗时**（另有 35 条数量不匹配、
   895 条确实没有内层数据）。

并发批次的判定规则：脚本内 `cmd:` 出现 N 次（N≥2）时，
若内层 `wall_time_seconds` 也正好 N 个 → 逐条对应，标 `self_reported`；
数量不匹配或缺失 → 全部标 `batch_shared`。

**`batch_shared` 的记录不参与 p50/p90/max**，只计入总量并在报告里标注。
均摊会让每条数据都是错的。

**验收**：四级占比与上表偏差 < 1 个百分点；`duration_source` 无空值。

### 3.3 状态判定

优先级从高到低，**高位命中即停**：

1. `exit_code`（解析 `Process exited with code N`，实测 26706 条有）
   → `exit_code == 0` 时**直接判 ok，绝不再看输出文本**
2. `tool_result_events.status`（实测 `completed` 14193、`errored` 216、
   空 34587）→ 非空即用
3. 文本启发式 → **只扫 stderr，不扫全量输出**

第 3 条的约束是原型踩坑换来的：初版扫全量输出，报错率虚高到 20.3%，
改成 exit code 优先后降到 15.6%。那 4.7 个百分点全是 grep 日志时
输出里出现 `error:` 造成的假阳性。

`failure_kind` 取值：`timeout` / `network` / `not_found` / `permission` /
`build` / `test` / `other`。

**验收**：`exit_code=0 AND status='failed'` 必须为 **0 条**（回归测试守住）。

### 3.4 归一化

- `program` / `subcommand`：tree-sitter-bash 提取。已验证对
  `cd /x && git log | head -3; VAR=1 npm run build 2>&1 || echo fail` 这类
  复合命令能正确提出 6 个程序名，`has_error=False`。
- `template` / `template_id`：Drain3 聚类。已验证 `git log --oneline -12`
  与 `-30` 归到同一 cluster。
- `command_group`：手维护的程序→分组表（vcs / build / test / net / pkg /
  search / fs / lint / container / db / other）。
- 脱敏：先跑 redact 再落库。模板化天然去掉字面量，但原始 `command` 列
  仍需过一遍 `Authorization:`、`token=`、`-p <password>` 等模式。

**验收**：tree-sitter 解析失败率 < 1%，失败的命令降级为「取第一个 token」
而非丢弃；`program` 空值率 < 1%。

### 3.5 M1 停止条件

全部满足即停，不追加功能：

- [ ] `cmdaudit extract` 对本机 1600 个会话跑通，耗时 < 2 分钟
- [ ] 抽取 51857 ± 200 条命令，`write_stdin`/`apply_patch` 零混入
- [ ] `duration_source` 四级占比符合 3.2 表格，偏差 < 1pp
- [ ] `exit_code=0 AND status='failed'` 为 0 条
- [ ] `program` 与 `duration_source` 无空值
- [ ] 单元测试覆盖：三种命令键名、JS 脚本三种引号、耗时四级降级、
      状态三级判定、并发批次 exact/mismatch/no_wall 三种分支
- [ ] 每个 agent 至少一个脱敏 fixture，codex 新旧格式都有
- [ ] `ruff` + `mypy` 干净

---

## 4. M2 聚合与报告

`cmdaudit report` 输出 `report.md` + `summary.json`。

维度：program / template / command_group / agent / project。
指标：count、total_ms、p50、p90、max、error_rate、timeout_rate、耗时占比。

默认按 `total_ms` 降序 —— 「哪条命令吃掉我最多时间」是第一诉求。

三张专项表：

1. **耗时榜** —— 按 template 聚合的总耗时 top 30
2. **失败榜** —— 按 `failure_kind` 分组，附真实错误片段样本
3. **超时榜** —— `failure_kind IN ('timeout','network')` 单列，
   这是最初的诉求（网络超时吃掉大量时间）

`batch_shared` 记录从分位数统计中排除，报告里显式标注受影响条数。

### M2 停止条件

- [ ] 三张专项表 + 五个维度的聚合表全部产出
- [ ] 报告里每个数字都能由文档附带的一条 SQL 复现
- [ ] 分位数统计已排除 `batch_shared`，报告中标注
- [ ] 在本机全量数据上跑通，`report.md` 可直接阅读

---

## 5. M3 模型分析

`cmdaudit analyze` 输出 `analysis.md`。

输入是 M2 的聚合结果 + 每个高开销模板的若干真实样本（含错误片段），
**不是全量命令** —— 51857 条塞不进上下文，也没必要。

要求模型按四段输出：

1. **必要性判定**：必要 / 可合并 / 可缓存 / 可删除，附依据
2. **耗时归因**：网络 / 磁盘 IO / 编译 / 等待进程 / 超时重试 / 参数误用
3. **预防措施**：能直接落进 `AGENTS.md`、脚本或 alias 的规则，给命令示例
4. **优先级**：按「节省时间 × 出现频率」排序取前 10

默认走本机已装的 agent CLI，数据不出本机（复用 agentsview insights 的思路）。

### M3 停止条件

- [ ] `analysis.md` 产出，四段结构完整
- [ ] 前 10 条建议每条都指向具体的 template 和实测数字
- [ ] **至少一条建议已落地并复测出耗时下降**（这是唯一的效果验证）

---

## 6. 总停止条件

M1 + M2 + M3 的 checklist 全绿，且满足：

- `README.md` 有可复制的 quickstart，新用户三条命令内看到报告
- `docs/schema.md` 记录 `commands` 表每一列的含义与取值来源
- CI 跑 `ruff` + `mypy` + `pytest`

**到这里就停。** M4 是可选项，需要新的明确需求才启动，不自动展开。

---

## 7. M4 可选增强（默认不做）

- 反哺 agentsview：M1 的归一化列若稳定，向上游提 PR。
  `tool_calls` 加列走 `migrateColumns()`（`internal/db/db.go:1066`），
  bump `dataVersion`（当前 59）。注意 PG 与 DuckDB 镜像 schema 要同步，
  否则 `pg push` 静默丢字段。
- 重试链检测：同 template 在窗口内重复且前次失败 → 标 `retry_of`
- 原始 JSONL 兜底解析器：agentsview 未覆盖的 agent
- OTel 接入：Claude Code 侧的精确耗时补充
- 趋势对比：两个时间窗口 diff，验证改进是否真的生效

---

## 8. 风险与应对

| 风险 | 应对 |
|---|---|
| Claude 侧无自报耗时（实测仅 1 条命中，Codex 44910 条），并行调用拿不到单条耗时 | `duration_source` 显式标记，报告区分精确值与推断值，不混用 |
| agentsview schema 变动（`dataVersion` 已 59，`user_version` 已 88） | 只读固定几列；启动时校验列是否存在，缺列直接报错而非静默出错数 |
| 命令含密钥 | 落库前脱敏；模板化天然去字面量；导出与分析前再过一遍 |
| 1.6 GB 库全量扫描慢 | 按 `session_id` 做 watermark 增量抽取 |
| `Bash` category 混入非命令（实测 25% 无命令键） | 白名单键名 + 显式排除 `write_stdin`/`apply_patch`，并在报告里报出排除条数 |
| Drain3 聚类粒度不合适 | 模板只作辅助分桶，主分桶键是 tree-sitter 给的 `program` + `subcommand` |
