# AGENTS.md · cmdaudit

统计 AI coding agent 会话里每条命令的耗时、退出码与失败原因，筛出值得做反事实实验的候选。
离线、只读、本机。Python 3.12+ CLI + React 工作台（编译为单文件 HTML 外壳）。

## 先读这些（按顺序）

1. 本文件 —— 红线与结果边界。
2. [`docs/handoff.md`](docs/handoff.md) —— 开发约定全文：门禁用法、环境坑、口径变更流程。
3. [`docs/plan.md`](docs/plan.md) §0（范围边界）与 §6（总停止条件）。
4. [`docs/project/system-map.md`](docs/project/system-map.md) —— 模块边界与数据流。
5. [`docs/visions/README.md`](docs/visions/README.md) —— 当前阶段、未交付事项、动手顺序。

## 结果边界（harness 约束，不可越界）

**交付边界 = 可复现的命令统计 + 值得做哪些实验的清单。越过这条线就是用未验证结论冒充证据。**

- `candidates.json` 每条记录恒为 `evidence_class: exploratory`、`status: unverified`，
  **不得计入任何质量声明**。让候选看起来像结论的改动一律返工。
- 本工具**不判定**「某条命令是否必要」，**不执行**反事实实验。二者都是下游职责
  （plan.md §5.1 / §6）。不要因为它们没做完而继续开发。
- 以下明确**不属于**交付范围，不作为继续开发的理由：
  候选是否真的冗余、改进后耗时是否下降、故障召回是否回退。
- M4（可选增强）默认不做，需要新的明确需求才启动。
- plan.md §0「不做」清单内的方向（token 统计、会话浏览 UI、fork agentsview、
  实时监控、自动执行建议）不要主动展开。

## 红线（违反即返工，全文与由来见 docs/handoff.md §1）

1. `exit_code == 0` 时绝不扫输出文本判失败。
2. 脱敏占位符必须是 shell 安全裸词（`REDACTED`，禁止 `<` `>`）。
3. 源库 `~/.agentsview/sessions.db` 一律 `mode=ro` 只读。
4. 脱敏发生在落库之前；测试 fixture 只准用合成凭据。
5. 运行时依赖上限 4 个（`tree-sitter-bash` / `tree-sitter` / `drain3` / `duckdb`），不引入 GPL。
6. 证据分级不可混：report/summary 是事实，candidates/triage 是假设。

## 门禁与验证基线

```bash
./scripts/check.sh    # 唯一权威入口（pin 版本，覆盖 CI 全部检查）
```

- 合并任何改动前 `check.sh` 全绿；CI 是事实来源。
- 涉及抽取或统计逻辑的改动，额外要求**全量 `extract` + `report` 实际跑通**，
  单测绿不算数（真实数据的形状多样性单测覆盖不到）。
- 别用系统装的 ruff/mypy/pytest；mypy 裸跑；**永远不要**整仓库 `ruff format`。
- `check.sh` 硬依赖网络，断网表现是挂住而不是快速失败。

## 前端（web/ ↔ src/cmdaudit/viz/）

- `src/cmdaudit/viz/shell.html` 是**构建产物**，与 `web/dist/index.html` 逐字节一致，
  CI 有同步校验。改前端后跑 `scripts/sync-shell.sh`；合并冲突不要手工解，重建同步。
- 数据契约**三侧**同步：`src/cmdaudit/viz/model.py` ↔ `web/src/lib/payload.ts`
  ↔ `web/src/lib/sanitize.ts`。前两者管类型，第三者是 whitelist 运行时校验 ——
  漏改 `sanitize.ts` 不会报错，字段会被**静默丢弃**。
- 视觉契约见 `DESIGN.md`：字重只 400/500、行高 ≤1.5、禁裸 Tailwind 圆角类、
  组件禁写死色值。语义色分两档：文字用 `--text-*`（4.5），
  边框/tint 底/图表笔画用 `--color-*`（3:1）。改色值必须实测，方法与四个
  采样陷阱写在 DESIGN.md「验收」。
- 产物必须 `file://` 双击可用：无 CDN、无外部字体、无埋点、无服务端。
- payload 唯一注入点是 `render_html.py` 的单次占位符替换，外部数据只走
  `serialize.payload_to_json`（已中和 `</script>`），不得新开文本出口。

## 数字口径纪律

- 改统计口径 = 旧数字全部作废（README、issue、截图）。用**同一快照**重跑
  全量 extract + report 后统一重写，不要中途逐步对数（plan.md §4 流程）。
- README 的实测数字对应快照日期，引用时说明口径与时刻。

## 已知未完成（详情见 docs/visions/README.md）

- 12 条 issue 修复分支在 `~/Documents/ChatGPT/cmdaudit` 本地未推送（入口顺序见该目录 HANDOFF 体系）。
- open issue 18 个，P0/P1 集中在口径对齐（#6/#11/#12/#13/#17）与前端形态（#7/#44/#49）。
- 2026-08-26 前端审查问题清单：`docs/reviews/2026-08-26-frontend-audit.md`。
  该文顶部有 2026-08-27 修正说明：其「对比度全部达标」是采样脚本缺陷导致的假结论，
  F-01（零运行时校验）已修。引用前先看修正。
