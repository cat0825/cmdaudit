# 系统地图 · cmdaudit

最后核对：2026-08-26，main @ `fef4e12`。以当前代码为准，与代码冲突时改本文。

## 数据流

```
~/.agentsview/sessions.db (只读 mode=ro)
        │  sources/agentsview.py   （白嫖 agentsview 的 20+ agent 解析器；duration/exit_code 从 result_content 补解析）
        ▼
extract/  command.py · shellparse.py(tree-sitter-bash) · duration.py(四级降级) · status.py(失败归因)
        │  normalize/  redact.py(落库前脱敏) · template.py(Drain3 聚类) · group.py(命令分组)
        ▼
store.py / db.py ──→ out/commands.duckdb（commands 表，schema 见 docs/schema.md）
        │
        ├─→ report/  queries.py · scope.py · build.py · render.py ──→ report.md + summary.json   【事实层】
        ├─→ screen/  rules.py(5 条确定性规则) · build.py · contract.py ──→ candidates.json/md   【假设层，恒 exploratory】
        └─→ viz/     collect.py(同源 SQL) ─→ model.py(Payload) ─→ serialize.py(注入安全) ─→ render_html.py ─→ report.html
                                                                                      ▲
                                                  web/ (React19+Vite+Tailwind4+Motion+Recharts) ──npm build──┘
                                                  产物复制为 viz/shell.html（构建物，CI 校验一致）
```

## 模块边界与职责

| 模块 | 职责 | 关键约束 |
| --- | --- | --- |
| `sources/` | 只读外部会话库 | `mode=ro`；不碰 agentsview daemon |
| `extract/` | 命令拆解、耗时四级降级（self_reported / turn_delta / batch_shared / unknown + duration_truncated 标记）、状态判定 | exit_code==0 不扫文本；`no_match` 不是失败 |
| `normalize/` | 脱敏（裸词占位符）、Drain3 模板聚类、命令分组 | 脱敏在落库前；fixture 只用合成凭据 |
| `report/` | 8 张聚合表，每张自带口径与可复现 SQL | 耗时与失败两套证据不跨表相加 |
| `screen/` | 候选筛选（非判定） | 契约**构造时**强制（contract.py 五类越界抛 `ContractViolation`） |
| `viz/` | 离线单文件工作台 | payload 唯一出口 `serialize.payload_to_json`；无 CDN/埋点 |
| `web/` | 工作台前端 | 见下方前端结构 |

## 前端结构（web/src）

- 入口 `App.tsx`：hash 路由八视图 + 全局键盘（1–4 改状态、j/k 移动、⌘K 面板）。
- 视图 `views/`：Overview（总览）/ Queue（失败模式）/ Board（四列看板，无拖拽）/
  Loops（重试循环）/ Groups（命令构成）/ Track（`duration` 耗时线与 `evidence`
  证据口径两个路由共用此文件）/ Candidates（验证队列）。路由清单以
  `web/src/lib/views.ts` 为准。
- 组件 `components/`：Rail 侧栏、Topbar、CommandPalette、DetailDrawer、FindingRow、CommandBlock、StatusPill、primitives。
- 图表 `charts/`：DurationHistogram / Heatmap / Sparkline / TrendChart（Recharts）。
- 状态 `lib/`：`payload.ts`（TS 契约 ↔ `viz/model.py`）、`load.ts`（注入读取+降级）、
  `sanitize.ts`（运行时 shape 校验 + 深层补全，降级原因回传页面）、
  `triage.ts`（localStorage 本机处理状态）、`theme.ts`（三态主题）、`format/views/motion`。
- 设计 token 全在 `styles.css`：语义色分两档 —— 文字档 `--text-*`（分主题派生，
  目标 4.5）与图形档 `--color-*`（主题无关，只做边框/tint 底/图表笔画）。
  单 accent（electric blue）只作交互色，不进图表数据笔画；Geist/Geist Mono
  内联 woff2；oklch 双主题；`prefers-reduced-motion` 尊重。视觉契约见 DESIGN.md。

## 高风险区（改动需升级验证）

- `extract/status.py`、`extract/duration.py` —— 口径语义，历史上多次量级级修正。
- `screen/contract.py` —— 证据分级的最后防线。
- `viz/serialize.py` —— 注入安全唯一出口。
- `web/src/lib/load.ts` + `sanitize.ts` —— payload 信任边界。运行时 shape 校验已落地
  （whitelist 收敛 + 降级告警），新增 payload 字段必须同时改 `sanitize.ts`，否则静默丢数据。

## 外部依赖

- 运行时仅 4 个：`tree-sitter-bash` / `tree-sitter` / `drain3` / `duckdb`（全 MIT）。
- 数据源 agentsview（MIT，不 fork）。原始 JSONL 兜底解析在 plan.md 中列为 M4 可选项，未做。
