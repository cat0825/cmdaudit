# DESIGN.md — cmdaudit

> 前端视觉契约。改 `web/` 下任何界面代码前先读这里。
> 数据契约、构建同步、口径纪律在 `AGENTS.md`，本文件只管视觉。

## 北极星

**午夜作战室里的终端。** 近黑画布上，一块亮色卡片像手电筒打下的一份调度单。
界面本身不说话，说话的是命令耗时、失败率、退出码。装饰性色彩为零：
每一处彩色都必须对应一个可判定的数据事实。

参考系：[Factory](https://styles.refero.design/style/13d6fc89-eba2-4724-ac37-20f4f2e5efec)
（refero 原文 "Terminal war room at midnight"）。下面的暗色 token 值取自该页实测，
偏离处在「与 Factory 的偏离」一节逐条列明理由。

## 适用范围

- 覆盖：`web/src/` 全部八个视图 —— `overview`（总览）/ `queue`（失败模式）/
  `board`（处理看板）/ `loops`（重试循环）/ `groups`（命令构成）/
  `duration`（耗时分析）/ `candidates`（验证队列）/ `evidence`（证据与口径），
  路由清单见 `web/src/lib/views.ts`。
  注意 `duration` 与 `evidence` 都由 `views/TrackView.tsx` 导出（`DurationView` /
  `EvidenceView`）—— 按文件名验收会漏掉两个视图。
  另覆盖图表（`charts/`）、组件（`components/`）、`web/src/styles.css` 的 token 层。
- 不覆盖：`docs/` 下的审查报告 HTML、README 截图。那些是文档产物，另有格式。
- 硬约束（来自 `AGENTS.md`，视觉决策不得违反）：
  - 产物必须 `file://` 双击可用 —— **无 CDN、无外部字体请求、无埋点**。
    新增字体只能 base64 内联进 `web/src/assets/`。
  - `src/cmdaudit/viz/shell.html` 与 `web/dist/index.html` 逐字节一致。
    改完前端跑 `scripts/sync-shell.sh`，不要手工改 shell.html。

## 与 Factory 的偏离（六条，都是有意的）

| # | Factory 规定 | cmdaudit 实际 | 理由 |
|---|---|---|---|
| 1 | 仅暗色主题 | 亮/暗双主题 | 已有能力，且 `docs/reviews/2026-08-26-frontend-audit.md` 记录双主题对比度全部达标。Factory 只做暗色权威，亮色按同结构派生。 |
| 2 | 零阴影，深度靠图底对比 | 暗色零阴影；亮色保留 `--shadow-card` / `--shadow-pop` | 亮色画布上「亮卡片压深背景」这招不成立，必须靠极轻阴影分层。 |
| 3 | 只用 Geist / Geist Mono，禁其他字族 | 字族栈末尾保留 `"Noto Sans SC"` | 界面有中文。Geist 无中文字形，不加 CJK 兜底会掉到系统随机字体。 |
| 4 | 主强调色 Signal Orange `#ee6018` | 交互色沿用现有 electric blue；橙/绿降为数据信号色 | 见下「强调色分工」。 |
| 5 | 区块间距 96px | **32–40px** | 审计面板是数据密集视图，96px 会把一屏能看的行数砍掉一半。 |
| 6 | 数据可视化统一走主强调色阶 | Heatmap 保留 `--color-danger-*` 单色阶 | Heatmap 画的是**失败**，不是「需注意的量级」。`charts/Heatmap.tsx:1-8` 的不变量是「当天没跑过（空槽虚线）」必须能和「跑了零失败（最浅一档实色）」区分开；换成最浅一档橙会削弱这个区分。语义正确性优先于色相统一。 |

### 不做 1200px 居中夹取（第七条偏离，单列说明）

Factory 规定内容区 `max-width: 1200px` 居中。cmdaudit **不做**：
rail 已经界定了左边界，`queue` / `board` / `duration` 三个视图是表格与多列看板，
宽度就是可读信息量；正文类长文本已经用 `max-w-[80ch]` / `max-w-[86ch]` 逐处夹取
（`views/TrackView.tsx:138,154,201`、`views/CandidatesView.tsx:35`）。
**不要给 `App.tsx` 的 `<main>` 加 `mx-auto` + 1200 夹取。**

### 强调色分工

Factory 的真正主张不是「用橙色」，而是**强调色只标数据，不填按钮**。
cmdaudit 已经在执行这条（审查结论：单 accent + 语义色只表状态判定），所以保留 blue
作交互色（焦点环、选中、可点），并按 Factory 收紧数据层：

- `accent-*`（electric blue，oklch 5 档）：**只用于交互可达性** —— focus ring、
  选中态、当前视图指示。不得进入图表数据笔画。
- `--signal-live`（橙）：**live 状态与图表主笔画**。不得作按钮填充、卡片底色、大字填充。
- 正向指标暂无对应 token，理由见「数据信号色」一节。
- `--chart-neutral`：图表里的非强调笔画（普通柱体、基线）。
- `danger` / `warn` / `ok`：沿用现有语义色，只表状态判定。
- 按钮主态用中性色：暗色 `--bg-elevated`，亮色 `--bg`。**任何情况下不用品牌色填充按钮。**

## 色彩

暗色主题直接采用 Factory 原值。变量名沿用 `web/src/styles.css` 现有语义层，
**组件不写死色值，只引 `var(--*)`**。

### 暗色（Factory 权威）

| 角色 | 变量 | 值 | 用在哪 |
|---|---|---|---|
| 画布 | `--bg` | `#101010` Obsidian | 页面底、rail 底 |
| 抬升面 | `--bg-elevated` | `#1d1a18` Carbon | 卡片、topbar、按钮填充 |
| 内凹面 | `--bg-inset` | `#171514` | 代码块、输入框 |
| 细线 | `--border` | `#3d3a39` Ash Stroke | 1px 分隔线、ghost 按钮描边 |
| 强线 | `--border-strong` | `#4d4947` Graphite Mid | 表头下沿、选中卡边 |
| 主文字 | `--text` | `#eeeeee` Bone | 正文、标题 |
| 次文字 | `--text-muted` | `#b8b3b0` Pale Stone | 段落说明、eyebrow |
| 弱文字 | `--text-faint` | `#8a8380` Warm Granite | 时间戳、禁用态 |
| 网格线 | `--grid-line` | `#2a2726` | 图表底格 |

`--border` / `--border-strong` / `--grid-line` 对卡片底只有 1.54 / 1.94 / 1.17，
**它们是分隔线，不是图形信息载体**。任何承载数据的图元（柱、线、点、色块）
不得使用这三个 token —— 走 `--chart-neutral`。

### 亮色（派生，非 Factory 原生）

沿用 `web/src/styles.css` 现有 oklch 面色（`--bg` / `--bg-elevated` / `--bg-inset`）不动，
oklch 便于统一调亮度。**不要为了「对齐 Factory」把亮色改成 hex。**

但**文字档不是原封不动的**：实测发现 `--text-faint` 原值 `oklch(0.62 …)` 对
`--bg-inset` 只有 3.28，已压到 `oklch(0.53 …)`（4.80，与暗色同档 `#8a8380` 的 4.78 齐平）。
语义色文字与焦点环也重新派生，见下面「语义色的两档分工」。

### 数据信号色（暗色权威，亮色派生）

橙 `#ee6018` 在暗色三种面上都过 AA，**在亮色上不成立**：对 `#ffffff` 只有 3.32。
所以信号色**不是双主题共用**，必须分主题定义。下表最差值 = 该主题
`--bg` / `--bg-elevated` / `--bg-inset` 三种面里的最小对比度。

| 变量 | 暗色值 | 暗色最差 | 亮色值 | 亮色最差 | 语义 |
|---|---|---|---|---|---|
| `--signal-live` | `#ee6018` | 5.21 | `oklch(0.55 0.18 37)` | 4.76 | 正在执行、需注意；图表主笔画 |
| `--chart-neutral` | `#6e6a67` | 3.23 | `oklch(0.64 0.005 258)` | 3.06 | 图表非强调笔画 |

**没有 `--signal-good`。** Factory 参考系里有一档 Metric Green `#a0ca92` 表「正向指标与
趋势」，但本产品的 payload 里不存在正向序列可绑：`FindingSignal` 只有 `failures`
（`src/cmdaudit/viz/model.py:140-144`），`TrendChart` 的两条序列是 `runs` 与 `failures`。
按本文件「新增色值先问：它对应哪个可判定的数据事实？答不出就别加」，这一档不定义。
将来若 payload 真的加了 delta / 改善序列，再按同样方式派生亮暗两值并实测。

- `--signal-live` 按**文字级 AA（≥4.5）**取值，所以既能画图元也能写数字。
- `--chart-neutral` 只到**图形级（≥3.0，WCAG 1.4.11）**，**禁止承载文字**。

### 语义色的两档分工（实测后新增）

`@theme` 里的 `--color-danger-*` / `--color-warn-*` / `--color-accent-*` / `--color-ok-*`
是**主题无关**的常量。拿它们直接写文字，必然有一个主题不达标 —— 实测值：

| 用法 | 暗色 | 亮色 |
|---|---|---|
| `--color-danger-500` 作 pill 文字 | 3.32 | 3.73 |
| `--color-accent-500` 作 pill 文字 | 3.96 | 3.30 |
| `--color-warn-400` 作 pill 文字 | 6.50 | **1.82** |
| `--color-accent-400` 作焦点环 | 6.44 | **2.44** |

所以分工固定为两档，**不得混用**：

- **图形档 `--color-*`**：边框、tint 底色、图表笔画。只需 1.4.11 的 3:1。主题无关。
- **文字档 `--text-danger` / `--text-accent` / `--text-ok` / `--text-warn`**：
  一切**文字与轴刻度**。分主题派生，按 4.5 取值。
  暗色档直接引用 `*-400` ramp（那一档本就为暗底设计，实测 4.65 / 5.43 / 6.47 / 6.50）；
  亮色档单独压暗到 `oklch(0.50–0.52 …)`。
- **`--focus-ring` / `--selection-bg` / `--selection-text`**：焦点环受 1.4.11 约束，
  同样分主题。选区要单独给前景色 —— 暗色环亮到 6.44 是好事，但白字压在上面只有 2.69，
  所以暗色选区用深色字（7.08），亮色用白字（5.77）。

亮色 pill 的 tint 底是 `color-mix(…, transparent)`，嵌在 `--bg-inset` 上会**再叠一层**
（详情抽屉里实测到 `rgb(247,228,230)`）。文字档必须按这个最深叠加面取值：
照白底反推会得到 `oklch(0.55 …)`，在抽屉里掉到 4.37。

⚠️ 上面所有数字是用 canvas 合成读回真实 sRGB 像素实测的，不是推算。
`getComputedStyle` 会原样返回 `oklch()` 字符串，**别拿正则当 RGB 解析** —— 那样
亮色主题会全部算成同一个错误比值。改任何色值或任何 `--bg*` 面色都要重新实测。
`docs/reviews/2026-08-26-frontend-audit.md` 的「WCAG AA 违规 = 0」已作废。

## 字体

两族，已 base64 内联在 `web/src/assets/`，不得新增第三族。

```
--font-sans: "Geist", ui-sans-serif, system-ui, "Noto Sans SC", sans-serif;
--font-mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
```

- **字重只用 400，强调才 500。禁止 600+。** Factory 的声音是「细字重 + 紧字距」，
  加粗会把作战室变成营销页。当前有 24 处违约（`font-semibold` × 23 + `font-bold` × 1），
  见「迁移清单」，**一次性改完，不要新旧混用**。
- 负字距随字号放大，见下表。
- **Geist Mono 全大写做 eyebrow** 是终端腔的核心：section eyebrow、状态标签、表格列头
  一律走 `eyebrow` 档。中文标签不做全大写（无大小写概念），改用 `--text-faint` + 字距 `0.05em`。
- 数字统一 `tabular-nums`（已在执行，保持）。命令文本、路径、`exit_code`、
  `duration_ms` 一律 mono。

### 字号阶梯（八档，数据密集面板）

不用 Factory 的落地页阶梯（72 / 44 / 36 …）—— 本产品实测最大字号是 24px
（`views/OverviewView.tsx:134` 的指标数字），16px 一处都没有，正文全在 11–12.5px。
72 / 44 / 36 在这个界面没有落点，写进来只会被忽略。

下表是对审查报告 A-02（「实测 12 个字号…建议收敛到 ≤ 8 档」）的处置：

| 角色 | 字号 / 行高 / 字距 | 落点 |
|---|---|---|
| metric | 24 / 1.0 / -0.02em | 指标大数字（`OverviewView`） |
| title | 14 / 1.3 / -0.01em | 视图标题、卡片标题 |
| body | 12.5 / 1.45 | 正文、列表主文本 |
| mono-cell | 12 / 1.4 / -0.02em | 命令原文、表格数字单元、输入框 |
| body-sm | 11.5 / 1.45 | 次级说明、徽标 |
| label | 11 / 1.2 | `dt` 标签、按钮文字 |
| eyebrow | 10 / 1.0 / 0.06em | mono 全大写 eyebrow、列头 |
| tertiary | 9.5 / 1.2 | 图例、脚注。**不得承载唯一信息**（A-02 点名 `BoardView.tsx:112`） |

被删除的档位：`10.5` / `13` / `13.5` / `15`。改前端时就近归并，**不要新增第九档**。

**行高不得超过 1.5。** 注意 Tailwind 的 `leading-relaxed` = **1.625**，超标，
当前有 16 处在用；改为 `leading-[1.45]` 或阶梯里对应的行高。

## 尺度与形状

基础单位 8px。间距阶梯：**8 / 16 / 24 / 32 / 40**。
（不列 56 以上 —— 区块间距上限已由第 5 条偏离定在 40px，列出来只会被误用。）

| 项 | Factory | cmdaudit 采用 |
|---|---|---|
| 内容区最大宽度 | 1200px 居中 | 不夹取，见第七条偏离 |
| 区块间距 | 96px | 32–40px |
| 卡片内边距 | 24px | 24px |
| 元素间距 | 24px | 16–24px（表格行内 16px） |

### 圆角

三档，全部走 token（`docs/reviews/2026-08-26-frontend-audit.md` A-04 记录当前无强制，
本文件即强制）：

| token | 值 | 用在哪 |
|---|---|---|
| `--radius-control` | **3px** | 按钮、pill、输入框、徽标 |
| `--radius-card` | **10px** | 卡片、面板、看板列 |
| `--radius-panel` | **20px**（新增 token） | drawer、command palette |

- **不得更软。** 现有 `--radius-card: 12px` / `--radius-control: 8px` 需一次性迁移。
- **禁止裸 Tailwind 圆角类**：`rounded-lg|md|xl|full|[Npx]` 一律换成
  `rounded-control` / `rounded-card` / `rounded-panel`。
- 豁免：`charts/Heatmap.tsx` 的 `rounded-[3px]` / `rounded-[2px]` 是**数据图元**
  （热力格与图例色块）不是控件，保留；`rounded-full` 用在状态圆点与进度条时保留。

## 深度

**暗色：零阴影 —— 包括 token 层。** `styles.css` 暗色块里 `--shadow-card` /
`--shadow-pop` 必须置为 `none`，不能只在组件里「别用」：只要 token 有值，
`hover:shadow-[var(--shadow-card)]`（`views/BoardView.tsx:100`）这类写法随手就能违约。
深度来自图底对比加 32px+ 留白，加 1px `--border` 细线。不要 glow、不要 blur、不要渐变。

**亮色：** 保留 `--shadow-card`（常态卡片）和 `--shadow-pop`（drawer / palette 浮层）。
两级封顶，不新增第三级。

## 项目绑定

token 落到具体文件，改动时按这张表对：

| 文件 | 视觉职责 |
|---|---|
| `web/src/styles.css` | token 唯一定义处。加色值只能加在这里。暗色 shadow 置 `none`；新增 `--radius-panel` 与三个信号色 token（双主题各一组）。 |
| `web/src/components/Topbar.tsx` | `--radius-control`，`--bg-elevated` 底，mono `eyebrow` 档 |
| `web/src/components/Rail.tsx` | **轨道在双主题下都保持深色** —— `Rail.tsx:1` 的既有意图（「它是产品的锚点，不随内容区翻转」）正好等于 Factory 的暗色权威，保留。所以 rail 走一组**主题无关**的 token（`--bg-rail` / `--rail-*`），只在 `:root` 定义一次，**不进 `[data-theme]` 覆盖块**；亮色主题下 rail 不变亮。当前 `:43,56,58,85,91` 五处硬编码 oklch 字面量必须全部迁走。选中态用 `accent`（交互色）不用橙。`:46` 的 `ca` 徽标同时踩「禁 600+」（`font-bold`）和「不用品牌色填充」（`--color-accent-500` 实底），改中性底 + 400 字重。 |
| `web/src/components/StatusPill.tsx` | `--radius-control`；`exit_code != 0` → danger，live → `--signal-live` |
| `web/src/components/CommandBlock.tsx` | mono，`--bg-inset` 底，命令原文不截断变形 |
| `web/src/components/DetailDrawer.tsx` | `--radius-panel`，亮色用 `--shadow-pop` |
| `web/src/components/CommandPalette.tsx` | `--radius-panel`，同上 |
| `web/src/components/primitives.tsx` | 按钮中性填充（暗 `--bg-elevated` / 亮 `--bg`），禁品牌色 |
| `web/src/charts/DurationHistogram.tsx` | 柱体 `--chart-neutral`（**不是 `--border-strong`**，后者对暗色卡片只有 1.94，低于图形 3:1）；超 p90 柱 `--signal-live`。改完同步改 `views/TrackView.tsx:202` 的说明文案 —— 那里现在写「用琥珀色标出」。 |
| `web/src/charts/TrendChart.tsx` | 主笔画 `--signal-live`；`failures` 序列保留 `--color-danger-500`（失败是语义色）。**渐变已删除** —— `<defs>/<linearGradient>` 整块移除，面积改成单一 `color-mix(in oklab, var(--signal-live) 14%, transparent)`，避免下个人把两个 stopOpacity 再拉开。 |
| `web/src/charts/Heatmap.tsx` | 保留 `--color-danger-*` 单色阶（第 6 条偏离）。不用彩虹色阶，不动空槽虚线。 |
| `web/src/charts/Sparkline.tsx` | 1px 笔画，无填充，无阴影 |
| `web/src/lib/theme.ts` | 主题切换逻辑，不含色值 |

## 迁移清单（当前违约实测数，改完应全部归零）

| 项 | 数量 | 位置 |
|---|---|---|
| `font-semibold` | 23 | 全仓 `web/src` |
| `font-bold` | 1 | `components/Rail.tsx:46` |
| `leading-relaxed`（1.625 > 1.5） | 16 | 全仓 `web/src` |
| 裸圆角类（`rounded-lg` 25 / `md` 3 / `xl` 1 / `[7px]` 3） | 32 | 全仓，扣除 Heatmap 豁免 |
| `rounded-card` 实际引用 | 仅 2 | `App.tsx:202`、`views/BoardView.tsx:58` —— token 层几乎没接进组件层 |
| Rail 硬编码 oklch | 5 | `components/Rail.tsx:43,56,58,85,91` |
| 超出八档的字号 | 4 档 | `10.5` / `13` / `13.5` / `15` |

## Do

- 每个区块都落在 `--bg` 上；只有卡片是亮的。
- 字重 400 打天下，标签必须压过周边时才 500。
- `--signal-live` 只出现在 live 状态和图表笔画。
- mono `eyebrow` 档全大写做 eyebrow / 状态标签 / 列头。
- 深度靠对比和留白，暗色一个阴影都不加（token 也置 `none`）。
- 新增色值先问：它对应哪个可判定的数据事实？答不出就别加。

## Don't

- 不要给按钮填品牌色或语义色。
- 不要用 600+ 字重、不要加粗中文标题。
- 不要在图表里用第三个数据色，也不要彩虹色阶。
- 不要用 `--border` / `--border-strong` / `--grid-line` 画数据图元。
- 不要用 `--chart-neutral` 写文字（它只到图形级 3:1）。
- 不要行高超过 1.5（含 Tailwind `leading-relaxed`）。
- 不要在暗色主题加阴影 / glow / blur / 渐变。
- 不要引第三个字族，不要引外部字体（会破 `file://`）。
- 不要为了「好看」把区块间距拉到 96px，这是数据面板不是落地页。
- 不要给 `<main>` 加 1200px 居中夹取。

## 验收

**入口是 `./scripts/check.sh`**（`AGENTS.md`：唯一权威入口，覆盖 CI 全部检查，
包含前端 typecheck、build，以及 `web/dist/index.html` ↔ `src/cmdaudit/viz/shell.html`
逐字节一致校验）。不要另起一串 `npm run typecheck && npm run build`：
`scripts/sync-shell.sh` 自己就跑 `npm ci` + `npm run build`，而 `npm run build`
已经是 `tsc -b && vite build` —— 串起来会跑三遍 tsc、两遍 vite build。

在仓库根执行（**用仓库相对路径，不要写绝对路径** —— 本机存在多个 cmdaudit clone）：

```bash
scripts/sync-shell.sh    # 重建外壳并落盘 shell.html（先跑，否则 check.sh 会在同步校验失败）
./scripts/check.sh       # 全量门禁
```

`check.sh` 硬依赖网络，断网表现是挂住而不是快速失败（`AGENTS.md`）。

视觉侧额外要求：

1. **对比度必须实测，不许推断。** 改了色值就在亮/暗双主题 × **八视图**
   × 两个断点（1440×900 / 720×900）重采样，外加**详情抽屉与 ⌘K 面板**
   （它们只在交互后才存在，静态扫页面扫不到）—— 共 40 个采样点。
   目标 WCAG AA（文字 4.5、图形 3.0）。八视图含 `duration` 与 `evidence`，
   二者都在 `TrackView.tsx` 里。

   采样有四个必须踩对的点，踩错会得到假的「全部达标」或假的「大面积违规」：
   - **别用正则解析 `getComputedStyle().color`。** Chrome 原样返回 `oklch(…)`，
     当 RGB 解析会把亮色主题全部算成同一个错误比值。用 1×1 canvas 把前景色
     合成到已知底色上，读回真实 sRGB 像素。
   - **背景要沿祖先链逐层合成**，直到遇到不透明层为止。pill 的
     `color-mix(…, transparent)` 底叠在 `--bg-inset` 上会比单层更深。
   - **合成的起点是 `body` 不是 `documentElement`。** `<html>` 的
     `background-color` 解析出来是 `rgba(0, 0, 0, 0)`，不透明画布色在 `body` 上。
     从 `<html>` 起算等于拿白色当底：暗色主题每个比值都被算反，
     `--text-accent` 会从 5.43 报成 2.45（症状：暗色一片违规而亮色全过）。
   - **路由 hash 是 `#overview`，不是 `#/overview`**，且要手动派发
     `hashchange`；写错会八个视图采到同一份 DOM（症状：各份结果计数完全相同）。
2. `file://` 双击打开 `web/dist/index.html`，确认字体正常、无网络请求。
3. 迁移做完后按「迁移清单」逐行 grep 归零，特别是裸圆角类与 `leading-relaxed`。

未做实测就不要在 PR 里写「对比度达标」。
