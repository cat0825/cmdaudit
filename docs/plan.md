# 实施计划

目标：回答三个**客观**问题 —— 我的 agent 都跑了什么命令、各花多长时间、
哪些失败了。第四个问题「哪些不必要」**不由本工具回答**，
它只输出待验证的候选假设，结论由下游的反事实实验给出（见 §5）。

本文档约束**实现方式**、**实现内容**、**停止条件**。
调研与选型依据见 [`research.md`](research.md)。

---

## 0. 范围边界

### 做

命令级审计：从已有会话记录里抽取每条 shell 命令，附耗时、退出码、失败归因，
聚合成可复现的统计，再筛出值得做反事实实验的候选。离线、只读、本机。

**证据等级**：M1/M2 产出的是客观事实（命令原文、耗时、退出码），
可直接引用；M3 产出的是待验证假设，标注 `evidence_class: exploratory`，
不得计入任何质量声明。

### 不做

- token / 成本统计 —— ccusage 已做透
- 会话浏览 UI —— agentsview 已做透
- fork agentsview —— 855 个 Go 文件且每天推送，维护成本远超收益
- 实时监控 / 常驻进程 —— 这是离线审计工具
- 自动执行改进建议 —— 只输出候选，改不改由人决定
- **判定某条命令「必要 / 不必要」** —— 无 ground truth，见 §5.1
- **反事实实验本身** —— 那是下游职责，cmdaudit 只负责选题

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
│   ├── cli.py              # argparse 入口：extract / report / screen
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
│   └── screen.py           # 候选筛选（输出假设，非结论）
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
        ├─ report ──→ report.md + summary.json       [客观事实，可直接引用]
        │
        └─ screen ──→ candidates.json                [待验证假设，exploratory]
                          │
                          └─→ 反事实实验（cmdaudit 之外）→ 才是结论
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

### 4.1 口径分离（M1 跑完后必须加的约束）

M1 全量跑完暴露一个事实，它决定了 M2 的结构：
**`self_reported` 的记录 100% 来自 codex**，
非 codex 的 14345 条命令里只有 7 条有自报耗时。

所以「精确耗时」和「跨 agent 覆盖」是互斥的，一个数字满足不了两者：

| 口径 | 含义 | 覆盖 | 用途 |
|---|---|---|---|
| `exact` | 仅进程自报墙钟 | 实际只有 codex | 耗时排名、分位数 |
| `upper_bound` | 叠加时间戳差值 | 全 agent | 只作量级参考，含模型思考时间 |
| `status_only` | 不用耗时证据 | 全 agent | 失败分析 |

**每张表必须打印自己的口径声明，混口径的汇总数字视为缺陷**，
由 `tests/test_report.py` 断言拦住。

失败线不依赖耗时，所以它是主线；耗时线是受限的补充。
这个顺序和原计划相反，依据是失败模式才能直接产出可写进 AGENTS.md 的规则。

### 4.2 耗时统计的三类排除

| 排除项 | 原因 | 实测条数 |
|---|---|---|
| `duration_source='batch_shared'` | 并发批次共享总墙钟，均摊会让每条失真 | 3422 |
| `duration_source='unknown'` | 无任何耗时证据 | 233 |
| `duration_truncated=true` | 命令未跑完就被工具让出，记到的是下界 | 3016 |

第三项是 M2 期间发现的 M1 缺陷：612 条自报耗时聚集在 30.0-30.5 秒，
那是工具 `yield_time_ms` 的让出上限，其中 473 条没有退出码 —— 命令确实没跑完。
判据是「无退出码 + 输出含仍在运行的标记」而非「耗时接近 30 秒」，
因为真跑了 30 秒又正常退出的命令是有效数据。

### 4.3 `no_match` 不是失败

同样在 M2 期间修正：`rg` / `grep` / `find` 退出码 1 表示查无结果，
`diff` / `cmp` 的 1 表示有差异，`which` / `type` 的 1 表示未安装。
这些都是**成功的查询得到否定答案**，不是命令失败。

不修的后果：`rg` 会以 133 次失败排进「最容易失败的程序」前列，
而它实际只有 38 次真失败。修正后新增 `status='no_match'`，
失败率榜的分母也排除它。

### 4.4 表清单

失败线（`status_only`，全 agent）：

1. **失败榜** —— `failure_kind` × `program`，附错误片段样本
2. **失败率榜** —— 仅统计已判定 ≥ 30 次的程序，分母排除 `unknown` 与 `no_match`
3. **超时/网络专项** —— 最初的诉求

耗时线（`exact`，仅自报墙钟）：

4. **耗时榜** —— 按 template 聚合 top 30
5. 五个维度聚合 —— command_group / program / agent / project

### M2 停止条件

- [x] 失败线三张表 + 耗时线五张表全部产出
- [x] 报告里每张表附带可复现的 SQL，测试断言重跑行数一致
- [x] 耗时统计排除 `batch_shared` / `unknown` / `duration_truncated`，报告中标注
- [x] 每张表打印口径声明，混口径由测试拦住
- [x] 在本机全量数据上跑通，`report.md` 可直接阅读

---

## 5. M3 候选筛选（不是判定）

`cmdaudit screen` 输出 `candidates.md` + `candidates.json`。

### 5.1 为什么不做「必要性判定」

原计划让模型输出「这条命令必要 / 可删除」。**这条路不通**，原因不是模型不准，
而是这种输出没有 ground truth：

当模型说「这条 `npm test` 没必要跑」，没有任何东西能证明它说对了。
「某个验证步骤是否必要」只能由「删掉它之后故障是否漏掉」来回答，
而模型没跑过那个反事实实验。

把模型判定当标签用会污染下游。以本仓库的消费方为例，
`src/cohort.mjs:8` 的 `EVIDENCE_CLASSES` 只接受 `planning` 与
`observed_benchmark` 两种证据等级，模型判定两者都不是；
`src/evaluation.mjs:451` 的效率声明还要求 `failure_recall` 不回退才成立。
硬塞模型判定等于绕过 fail-closed 检查从侧门放行未验证结论。

### 5.2 改成筛选器

| 用法 | 链条 | 是否可行 |
|---|---|---|
| 当**标签** | 模型说不必要 → 记为不必要 → 进数据集 | 不可行，无 ground truth |
| 当**筛选器** | 模型说可疑 → 反事实实验验证 → 验证过的才进数据集 | 可行 |

模型的职责是把 51857 条压缩到值得做实验的 200 条，降低的是**搜索成本**，
不是证据门槛。

### 5.3 输出契约

每条候选必须是**可验证的假设**，不是结论：

```json
{
  "template_id": "t_0421",
  "template": "sleep <n>; tail -<n> <path>",
  "observed": { "count": 45, "total_s": 1636.1, "pct_of_shell_time": 14.4 },
  "hypothesis": "轮询等待可由事件通知替代，节省等待时间",
  "verification": {
    "method": "counterfactual_run",
    "design": "同一任务跑两个 run，一个用 sleep 轮询一个用事件回调，比较总耗时与故障召回",
    "oracle": "independent_oracle"
  },
  "evidence_class": "exploratory",
  "status": "unverified"
}
```

硬约束：
- `evidence_class` 恒为 `exploratory`，**不允许出现 `observed_benchmark`**
- `status` 初始恒为 `unverified`，只能由外部反事实实验改写
- 措辞必须是「疑似 / 待验证」，禁止「不必要 / 应删除」这类判决式表述
- 每条必须带 `verification.design`，给不出验证方式的候选直接丢弃

### 5.4 M3 停止条件

- [ ] `candidates.json` 产出，schema 校验通过
- [ ] 每条候选都带 `verification.design` 与 `evidence_class: exploratory`
- [ ] 无任何一条候选的 `status` 为 `verified`（那只能由实验写入）
- [ ] 回归测试：断言输出里不含 `observed_benchmark`、不含判决式措辞
- [ ] 候选按「潜在节省时间 × 出现频率」排序，前 20 条人工可读

**注意这里没有「至少一条建议已落地并复测出耗时下降」这一项。**
效果验证不属于 cmdaudit 的职责，它属于下游的反事实实验。
cmdaudit 的交付到「给出该做哪些实验」为止。

---

## 5.5 一个已经浮现的信号：靶子可能放错了

原型（3836 条命令 / 11345s shell 时间）的类别耗时分布：

| 类别 | 耗时占比 | 条数 | 说明 |
|---|---:|---:|---|
| other | 23.1% | 465 | 头部是 `for` 循环 1190s、`npx` 694s |
| proc_sys | 15.5% | 132 | **头部是 `sleep` 1636s** |
| net | 12.7% | 411 | 网络等待 |
| search_read | 11.9% | 1732 | 条数最多但 p90 仅 0.58s |
| pkg | 9.0% | 143 | |
| **test** | **8.8%** | 143 | |
| vcs | 8.7% | 512 | |

`other` + `proc_sys` 合计 **38.6%**，而 `test` 只有 8.8%。

深挖 `proc_sys` 的头部，`sleep` 45 次吃掉 1636s，占全部 shell 时间的
**14.4%**，形态全是：

```
sleep 180; tail -5 <task 输出文件>
sleep 150; tail -3 <task 输出文件>
sleep 90;  gh pr view 118 --json mergeStateStatus
```

这是等后台任务时的轮询等待 —— **纯等待，零信息产出**，
而且单条最长 180s。

这个数字的意义比「哪条测试不必要」大得多：如果下游实验全部围绕测试命令设计，
最好情况也只能改善那 8.8%。**扩大实验规模之前，应先确认靶子位置。**

需要说明两点边界：

1. 这是**探索性信号**（`evidence_class: exploratory`），样本仅 3836 条命令、
   单机单人，不能外推。
2. `other` 类里的 `for` / `#` / `-v` 是原型解析器的**误判** ——
   `command -v codex` 被当成程序名 `-v`，heredoc 里的注释被当成命令。
   这正是 M1 用 tree-sitter-bash 替代 shlex 的直接理由。
   修正后 `other` 的占比会下降，但 `sleep` 那 14.4% 不受影响，它是真实的。

---

## 6. 总停止条件

M1 + M2 + M3 的 checklist 全绿，且满足：

- `README.md` 有可复制的 quickstart，新用户三条命令内看到报告
- `docs/schema.md` 记录 `commands` 表每一列的含义与取值来源
- CI 跑 `ruff` + `mypy` + `pytest`
- **证据等级分离**：M1/M2 输出不含任何模型生成内容；
  M3 输出的每条记录都带 `evidence_class: exploratory` 与 `status: unverified`

**到这里就停。** M4 是可选项，需要新的明确需求才启动，不自动展开。

### 明确不作为停止条件的事项

以下都**不属于** cmdaudit 的交付范围，不要因为它们没做完而继续开发：

- 某条候选是否真的冗余 —— 需要反事实实验
- 改进后耗时是否真的下降 —— 需要 baseline/candidate 双跑对比
- 故障召回是否回退 —— 需要独立 oracle

cmdaudit 的交付边界是「给出可复现的命令统计 + 值得做哪些实验」。
越过这条线就是在用未验证结论冒充证据。

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
