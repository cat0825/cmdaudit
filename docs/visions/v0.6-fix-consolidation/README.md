# v0.6-fix-consolidation · 修复整合期

**目标**：把已完成但未交付的修复合并到 main，统一口径数字，关掉对应 issue。
**不交付新功能。**

## 范围锚点

- 进入本阶段时的状态：`~/Documents/handoff-cmdaudit-2026-08-25.md`（历史证据，
  其中 PR #48 已完成合并，其余仍然有效）。
- 修复施工树：`~/Documents/ChatGPT/cmdaudit`（12 条 fix 分支 + 13 个 commit）。
- 本仓库（`~/Documents/GitHub/cmdaudit`）已与远端 main 同步。

## 动手顺序（继承 08-25 交接，逐对经 merge-tree 核实）

| 步骤 | 入口分支 | 带进的 issue |
| --- | --- | --- |
| 1 | `fix/issue-7-m5-product-form` | #7 |
| 2 | `fix/issue-6-duration-scope` | #6 |
| 3 | `fix/issue-23-candidates-contract`（栈A顶） | #11→#21→#22→#23 |
| 4 | `fix/issue-17-real-calendar-window`（栈B顶） | #13→#12→#17 |
| 5 | `fix/issue-24-scope-and-incremental` | #24 |
| 6 | `fix/issue-30-truncation-config` | #30 |
| 7 | `fix/issue-29-agent-fixtures` | #29 |

**别按编号顺序合，按上表合**（#7 是六个前端 issue 的形态前置）。
栈内中间分支不单独合但别删（现成切分点）。

合并操作要点（实测踩出）：

1. `src/cmdaudit/viz/shell.html` 是构建产物——冲突随便取一边，然后 `scripts/sync-shell.sh` 重建，否则一致性检查红。
2. `README.md` 每步都冲——中途随便取一边，全部合完后同一快照重跑 extract+report 统一重写数字。
3. `docs/plan.md` / `docs/schema.md` 冲突是新增段落相邻，两边都留。

## 验收（本阶段 Done 的定义）

- [ ] 12 条分支全部合并推送，CI 绿
- [ ] `./scripts/check.sh` 全绿
- [ ] 同一快照全量 extract + report 重跑，README 数字统一重写
- [ ] 对应 issue 逐条关闭并在 #46 记录落地
- [ ] 勾掉 `docs/plan.md` §7.5.6 的四笔已知欠账（#6/#17/#18/#21）
- [ ] 处理悬空 `uv.lock`（提交或 ignore 二选一）

## 明确不做

- 不启动 M4 / M6–M8（#47 只是路线文档）。
- 不做 #44/#45/#49/#50（合并完再排期）。
- 不重构、不搬文档、不整仓 `ruff format`。

## 当前风险

- 合并期间 README 数字与代码短暂不一致——以合并后重跑为准，不要中途对数。
- triage localStorage 与 finding identity 的孤儿化问题（#12/#21/#44 交叉）在合并后需复验。

## Session Handoff

- 2026-08-26：本目录与 AGENTS.md / system-map 建立；前端审查落盘
  `docs/reviews/2026-08-26-frontend-audit.md`；main 全量复跑 + check.sh 全绿。
  下一步 = 按上表合并 12 条分支。
