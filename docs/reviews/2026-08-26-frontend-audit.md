> **后续修正（2026-08-27）**：本文两处结论已被更严格的复测推翻，正文保留原样
> 作为当时的记录，不要据此判断当前状态。
>
> 1. **「双主题对比度全部达标 / WCAG AA 违规 = 0」是假结论**（见下方总体结论与
>    「达标项」）。当时的采样脚本用正则解析 `getComputedStyle().color`，而 Chrome
>    原样返回 `oklch(…)` 字符串 —— 亮色主题被整体算成同一个错误比值。改用 canvas
>    读回真实 sRGB 像素后实测到多处真实违规，最低 1.82（`--color-warn-400` 作亮色
>    文字）。修法是把语义色拆成文字档 `--text-*` 与图形档 `--color-*` 两档，
>    详见 `DESIGN.md`「语义色的两档分工」与该文「验收」章节列出的四个采样陷阱。
> 2. **F-01「零运行时校验」已修**：`web/src/lib/sanitize.ts` 落地了 whitelist 收敛
>    与降级告警，`load.ts` 的两个出口都过它。
>
> 另外本文按「六视图」描述前端，现为八视图（新增 `loops` / `groups`），
> 路由清单以 `web/src/lib/views.ts` 为准。

# 前端审查 · 2026-08-26

**范围**：`web/src`（React 19 + TS，~2,400 行）对照 `src/cmdaudit/viz/{model,serialize,collect,render_html}.py`，
逻辑与审美两个维度。**方法**：全量通读 + 当前 main 全量复跑生成 report.html 后在真实浏览器
（1440×900 / 720×900、亮/暗双主题）程序化实测：对比度、字体、横向溢出、布局链。
结合 open issue #21/#23/#44/#45/#49/#50 做代码佐证。

**总体结论**：无无条件白屏路径，常规边界（空数组、null、除零、非法日期）都防住了；
设计 token 纪律高于平均水平（单 accent、语义色只表状态、双主题对比度全部达标）。
系统性短板两个：**payload 信任边界画错位置**（前端把"同源 Python 生成"当免验证理由，
与 issue #23 自相矛盾）和**键盘作用域没有统一仲裁**（三个组件各自挂 window 监听，缝隙在层间漏出）。

---

## 一、逻辑 Findings（按严重度）

### P1 错误行为

**F-01 payload 浅合并 + 零运行时校验，深层缺字段直接白屏**
`web/src/lib/load.ts:25-26,32-33` —— `{ ...EMPTY_PAYLOAD, ...parsed }` 是浅合并：
payload 顶层有 `dashboard` 但缺 `heatmap_agents`（旧版 Python + 新外壳、或手改 report.html）时，
合并后该字段为 undefined，`charts/Heatmap.tsx:38` 的 `.map` 抛 TypeError 整页白屏。
同理 `findings` 非数组时 `App.tsx:116` 的 `.filter` 直接炸。这正是 issue #23 要求的前端侧验证。
**修复**：递归 deep-merge EMPTY_PAYLOAD，或 load 出口做轻量 shape 校验，失败降级 EMPTY 并显式告警。

**F-02 issue #23 佐证：前端硬编码合规声明**
`web/src/views/CandidatesView.tsx:16-18` —— `evidence_class = exploratory` 徽标是写死的字符串；
`Candidate` TS 类型（`lib/payload.ts:49-58`）与 Python dataclass（`model.py:84-95`）都没有
`evidence_class`/`status` 字段，`_load_candidates`（`collect.py:356-378`）也不读。三层共谋：
损坏/伪造的 candidates.json 会被页面显示为合规 exploratory。
**修复**：按 #23 验收——schema 版本化 + viz 加载时验证 + 徽标改从已验证字段渲染。

**F-03 关闭抽屉后 selectedId 残留，1–4 可改写不可见项**
`web/src/App.tsx:51-53` 的清理 effect 只在 view 变化时触发。路径：Board 点开卡片 →
`openFinding` 同时 `setSelectedId`（:81）→ 关抽屉只清 `openId`（:211）→
`activeId = openId ?? selectedId`（:105）仍指向那条 finding → 按 1–4 改写一条
屏幕上没有任何选中指示的记录。`:48-50` 注释声明已防住这类问题，实际只防了切视图。
**修复**：关抽屉时若非 queue 视图一并清 selectedId。

**F-04 CommandPalette 退出动画是死代码**
`web/src/components/CommandPalette.tsx:107` —— `if (!open) return null` 在 return
`AnimatePresence`（:116）之前，open 变 false 瞬间整树卸载，:122/:134 的 exit variants
永不播放。正确写法见 `DetailDrawer.tsx:32-33`（条件渲染放 AnimatePresence 内部）。

### P2 体验/局部错误

**F-05 复制按钮在 file:// 下静默失败，fallback 不可达**
`web/src/components/CommandBlock.tsx:25-28` —— `navigator.clipboard.writeText` 存在但 reject
时走 `.catch(() => undefined)`，不进 execCommand 回退，无失败反馈。
**本产品主分发形态就是 file:// 离线 HTML，即主路径上复制是坏的。**

> **2026-08-26 修复时实测更正**：原文把 reject 归因于「file:// 非安全上下文」，错。
> Chromium 把 file:// 当可信来源，`isSecureContext === true`、`navigator.clipboard` 存在；
> 实际拒绝是 `NotAllowedError`，触发条件是文档未聚焦 / 权限策略 / 无用户激活。
> 缺陷本身（静默失败、回退不可达）成立，归因需改。修复见 issue #55。

**F-06 抽屉页脚提示 J/K"上下条"，但 j/k 只动选择不动抽屉内容**
`web/src/components/DetailDrawer.tsx:198-202` vs `QueueView.tsx:154-162`：j/k 只改
selectedId，抽屉渲染 openId（`App.tsx:127`），内容原地不动。提示与行为不符。

**F-07 批量勾选被筛选条件静默裁剪**
`web/src/views/QueueView.tsx:187` —— `checkedIds` 只保留可见行。勾选 5 条后加筛选隐藏 3 条，
批量条显示"已选 2 条"且只对 2 条生效，用户无从得知。
**修复**：显示"已选 5（当前可见 2）"并对全部生效，或筛选变化时清空勾选集。

**F-08 抽屉"首次/末次"在 null 时渲染成 `" → "`**
`web/src/components/DetailDrawer.tsx:92` —— `formatDay(null)` 返回 `"—"`，`.slice(5)` 得空串。
`first_seen`/`last_seen` 在 started_at 不可解析时可为 null（`collect.py:584-585`）。

**F-09 issue #49 佐证：remedy 无专属呈现**
`Candidate.observed` 是 `Record<string, unknown>` 整体透传（`collect.py:375`），
`CandidatesView.tsx:70-81` 把 observed 渲染成无差别键值格子，remedy 与诊断字段挤在一起；
`:78` `String(value ?? "—")` 对嵌套对象输出 `[object Object]`。
**修复**：按 #49 加归并后的 remedy 区块；observed 对 object 做 JSON.stringify 兜底。

**F-10 面板打开时队列的 j/k/方向键仍在后台生效**
`web/src/views/QueueView.tsx:149-151` 守卫只看 tagName，不感知 palette/drawer 打开状态；
焦点在遮罩后时按 j 会移动选中行，Enter（:163）还可能开抽屉。
**修复**：键盘监听收敛到 App 单点仲裁，palette/drawer 打开时队列短路。

### P3 建议/加固

**F-11 issue #21 三宗罪全部命中**：`lib/triage.ts:34` storage key 只取 basename（所有
`commands.duckdb` 串用）；:61-64,:70-72 读写失败静默吞掉，UI 无"未保存"指示
（`DetailDrawer.tsx:110-112` 反而写"存本机浏览器"）；无导出导入；
`STATUS_LABEL.verified = "已确认"`（:17）与 screen 契约禁止的 verified 语义撞名。

**F-12 issue #44/#45/#50 前端侧佐证**
- #44：`finding_id = template_id:failure_kind`（`collect.py:575`）挂在 Drain3 聚类上，
  模板漂移时 triage 条目静默孤儿化；无"新增"筛选、无孤儿清理。
- #45：单文件架构 + `load.ts` 首帧全量注入 + 无 `React.lazy`，tracks ~690KB 无法按需——
  修复面在 Python/打包层，不在前端组件。
- #50：纯 Python 归一化 bug，前端被动承受，无次生崩溃（key 靠 candidate_id 仍唯一）。

**F-13 魔法字符串键**：`App.tsx:126`、`OverviewView.tsx:51-52,61,66,80-81` 硬编码
`"命令总数"` 等中文 coverage 键；Python `report/build.py:22-37` 改名即静默归零
（`numberOf` 把非 number 归为 0）。**修复**：coverage 改固定英文键 + 显示标签分离。

**F-14 `TrackView.tsx:222`** —— `(value ?? "—")` 若 Python 侧某天塞 dict/list，
React 19 对 object child 直接 throw 白屏。当前只产标量所以不炸，与 F-01 同属"契约靠默契"。

**F-15 小项**：`App.tsx:79-86` openFinding 对不存在的 id 仍 setSelectedId；
`Row.cells` 混入 bool 时 `TrackView.tsx:17-21` 渲染为空格（加 String 兜底）；
`theme.ts:61-63` `cycle()` 是死代码。大列表无虚拟化**不是问题**
（MAX_FINDINGS=120、MAX_CANDIDATES=24、heatmap 8×30 都有硬上限）。

---

## 二、审美 Findings（真实浏览器实测）

实测环境：main 全量复跑的 report.html，Chromium，1440×900 与 720×900，亮/暗双主题，
覆盖六视图全部。

### 达标项（实测通过，不要改）

- **对比度**：六视图 × 双主题全量文本采样，WCAG AA 违规数 = 0（含 9.5px 最小字）。
- **字体纪律**：全站仅 Geist + Geist Mono 两族，base64 内联，file:// 可用；数字统一 tabular-nums。
- **色彩纪律**：单 accent（electric blue oklch 5 档）+ 语义色只表状态判定；无渐变滥用、无第二强调色。
- **主题**：system/light/dark 三态 + localStorage 覆盖，实现正确（`theme.ts`）。
- **可及性**：`:focus-visible` 焦点环、`prefers-reduced-motion` 全局降级、键盘可达看板（不做拖拽是有意决策）。
- **横向溢出**：1440px 下六视图全部无溢出。

### A-01（P1）窄视口看板/耗时视图横向溢出——已定位根因并验证修法

**现象**：视口 < lg（1024px）时，Board 与 Track 视图出现整页横向滚动
（720px 视口实测 `scrollWidth = 8651`）。

**根因**：`BoardView.tsx:47` 的 `grid lg:grid-cols-4` 在单列态下，grid item（`BoardView.tsx:54` 的
section）保留默认 `min-width: auto`；列内最长 `finding.template` 达 1243 字符，
`<code class="clip">`（:103）nowrap 文本的 min-content 贡献沿 LI→UL→SECTION 一路上传，
把 grid 轨道撑到 8628px。**实测验证**：给 section 加 `min-width: 0` 后 scrollWidth 8651 → 710，立即修复。

**对照**：`QueueView.tsx:295` 与 `FindingRow.tsx:53` 的网格已正确使用 `minmax(0,1fr)`，
所以队列不溢出——同仓库两种写法，说明这是疏漏不是知识缺口。

**修复**：`BoardView.tsx:54` section 加 `min-w-0`（一行）；`TrackView.tsx:48` 的
`code.clip` 所在表格单元同样检查（表格布局建议 `table-fixed` 或包一层 min-w-0）。

### A-02（P2）类型刻度碎片

实测 12 个字号（9.5 / 10 / 10.5 / 11 / 11.5 / 12 / 12.5 / 13 / 13.5 / 14 / 16 / 24），
半档步进本身一致，但对一个六视图工具偏多；9.5px 已低于舒适阅读线
（Board 卡片次级信息 `BoardView.tsx:112`）。数据密集型内部分析工具可接受，
建议收敛到 ≤ 8 档并把 9.5px 只留给 truly-tertiary 内容。

### A-03（P2）file:// 下复制静默失败（审美层是"反馈缺失"）

见 F-05。逻辑是 catch 吞掉，体验是点了没反应——主分发形态上的核心交互没有反馈环。
修复时一并加视觉确认（copied 态）。

### A-04（P3）圆角 token 使用基本一致但无强制

`rounded-card`(12px) / `rounded-lg`(8px) / pill 为主，混有零散 `rounded`（4px）与 3px 元素。
可接受；若再出新组件，沿用现有两档即可。

---

## 三、优先修复建议

1. **F-01 + F-02**（一起修）：load 层 shape 校验 + candidates 契约验证——这俩修完，
   issue #23 的前端侧就闭环了，P2/P3 里一半问题失去土壤。
2. **A-01**：一行 `min-w-0`，收益是窄窗口下两个视图从"坏"变"好"。
3. **F-03 + F-06 + F-10**：键盘仲裁收敛到 App 单点。
4. **F-05**：file:// 复制回退 + 反馈。

## 未验证项

- 未跑 `npm run dev` 热更新路径（只验证了构建产物）。
- 截图级像素审查未做（本次为计算样式级审查）；motion 动画的帧率表现未量化。
- Safari/Firefox 未测（oklch 与 singlefile 在旧浏览器的表现）。
