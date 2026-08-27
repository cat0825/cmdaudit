# DESIGN.md — cmdaudit

> 前端视觉契约。改 `web/` 下任何界面代码前先读这里。
> 数据契约、构建同步、口径纪律在 `AGENTS.md`，本文件只管视觉。

## 北极星

**午夜作战室里的终端。** 近黑画布上，一块亮色卡片像手电筒打下的一份调度单。
界面本身不说话，说话的是命令耗时、失败率、退出码。装饰性色彩为零：
每一处彩色都必须对应一个可判定的数据事实。

参考系：[Factory](https://styles.refero.design/style/13d6fc89-eba2-4724-ac37-20f4f2e5efec)
（refero 原文 "Terminal war room at midnight"）。下面的 token 值取自该页实测，
偏离处在「与 Factory 的偏离」一节逐条列明理由。

## 适用范围

- 覆盖：`web/src/` 全部视图（Overview / Board / Candidates / Queue / Track）、
  图表（`charts/`）、组件（`components/`）、`web/src/styles.css` 的 token 层。
- 不覆盖：`docs/` 下的审查报告 HTML、README 截图。那些是文档产物，另有格式。
- 硬约束（来自 `AGENTS.md`，视觉决策不得违反）：
  - 产物必须 `file://` 双击可用 —— **无 CDN、无外部字体请求、无埋点**。
    新增字体只能 base64 内联进 `web/src/assets/`。
  - `src/cmdaudit/viz/shell.html` 与 `web/dist/index.html` 逐字节一致。
    改完前端跑 `scripts/sync-shell.sh`，不要手工改 shell.html。

## 与 Factory 的偏离（四条，都是有意的）

| # | Factory 规定 | cmdaudit 实际 | 理由 |
|---|---|---|---|
| 1 | 仅暗色主题 | 亮/暗双主题 | 已有能力，且 `docs/reviews/2026-08-26-frontend-audit.md` 记录双主题对比度全部达标。Factory 只做暗色权威，亮色按同结构派生。 |
| 2 | 零阴影，深度靠图底对比 | 暗色零阴影；亮色保留 `--shadow-card` / `--shadow-pop` | 亮色画布上「亮卡片压深背景」这招不成立，必须靠极轻阴影分层。 |
| 3 | 只用 Geist / Geist Mono，禁其他字族 | 字族栈末尾保留 `"Noto Sans SC"` | 界面有中文。Geist 无中文字形，不加 CJK 兜底会掉到系统随机字体。 |
| 4 | 主强调色 Signal Orange `#ee6018` | 交互色沿用现有 electric blue；橙/绿降为数据信号色 | 见下「强调色分工」。 |

### 强调色分工

Factory 的真正主张不是「用橙色」，而是**强调色只标数据，不填按钮**。
cmdaudit 已经在执行这条（审查结论：单 accent + 语义色只表状态判定），所以保留 blue
作交互色（焦点环、选中、可点），并按 Factory 收紧数据层：

- `accent-*`（electric blue，oklch 5 档）：**只用于交互可达性** —— focus ring、
  选中态、当前视图指示。不得进入图表数据笔画。
- Signal Orange `#ee6018`：**live 状态与图表主笔画**。不得作按钮填充、卡片底色、大字填充。
- Metric Green `#a0ca92`：正向指标与趋势。同样禁止按钮填充。
- `danger` / `warn` / `ok`：沿用现有语义色，只表状态判定。
- 按钮主态用中性色：暗色 `#1f1d1c`，亮色 `#fafafa`。**任何情况下不用品牌色填充按钮。**

⚠️ 引入橙/绿到图表笔画后，**对比度必须重新实测**，不要沿用旧结论。
`docs/reviews/2026-08-26-frontend-audit.md` 的「WCAG AA 违规 = 0」是改动前的数字，
换了图表配色即作废。

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

### 亮色（派生，非 Factory 原生）

沿用 `web/src/styles.css` 现有 oklch 亮色值，不动。它已通过对比度实测，
且 oklch 便于统一调亮度。**不要为了「对齐 Factory」把亮色改成 hex。**

### 数据信号色（双主题共用）

| 角色 | 值 | 语义 |
|---|---|---|
| live / 图表主笔画 | `#ee6018` | 正在执行、需注意 |
| 正向指标 | `#a0ca92` | 耗时下降、成功率上升 |
| 失败 | `--color-danger-*` | `exit_code != 0` |
| 告警 | `--color-warn-*` | 超时、可疑必要性 |
| 告警文字 | `--text-warn` | **浅底上的告警文字只能用这个**，`--color-warn-400` 在浅底只有 1.8:1 |

## 字体

两族，已 base64 内联在 `web/src/assets/`，不得新增第三族。

```
--font-sans: "Geist", ui-sans-serif, system-ui, "Noto Sans SC", sans-serif;
--font-mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
```

- **字重只用 400，强调才 500。禁止 600+。** Factory 的声音是「细字重 + 紧字距」，
  加粗会把作战室变成营销页。
- 负字距随字号放大：72px 用 `-0.04em`，12px 用 `-0.02em`。
- **Geist Mono 12px 全大写**是终端腔的核心：section eyebrow、状态标签、表格列头
  一律走这个。中文标签不做全大写（无大小写概念），改用 `--text-faint` + 字距 `0.05em`。
- 数字统一 `tabular-nums`（已在执行，保持）。命令文本、路径、`exit_code`、
  `duration_ms` 一律 mono。

### 字号阶梯（Minor Third，14px 基准）

| 角色 | 字号 / 行高 / 字距 |
|---|---|
| display | 72 / 1.0 / -2.88px |
| heading-lg | 44 / 1.12 / -1.1px |
| heading | 36 / 1.1 / -1.12px |
| body | 16 / 1.5 |
| body-sm | 14 / 1.43 |
| caption | 12 / 1.0 / -0.24px |

**行高不得超过 1.5。**

## 尺度与形状

基础单位 8px。间距阶梯：8 / 16 / 24 / 32 / 40 / 56 / 80 / 96 / 120。

| 项 | Factory | cmdaudit 采用 | 说明 |
|---|---|---|---|
| 最大宽度 | 1200px | 1200px | 一致 |
| 区块间距 | 96px | **32–40px** | 审计面板是数据密集视图，96px 会把一屏能看的行数砍掉一半。这是第五条偏离。 |
| 卡片内边距 | 24px | 24px | 一致 |
| 元素间距 | 24px | 16–24px | 表格行内用 16px |

圆角（`docs/reviews/2026-08-26-frontend-audit.md` A-04 记录当前无强制，本文件即强制）：

- 按钮 / pill / 输入框：`--radius-control`，改为 **3px**
- 卡片 / 面板：`--radius-card`，改为 **10px**
- 最大面板（drawer、palette）：**20px**
- **不得更软。** 现有 12px / 8px 需一次性迁移，不要新旧混用。

## 深度

**暗色：零阴影。** 深度来自图底对比（`#eeeeee` 卡片压在 `#101010` 画布上）
加 32px+ 留白，加 1px `--border` 细线。不要 glow、不要 blur、不要渐变。

**亮色：** 保留 `--shadow-card`（常态卡片）和 `--shadow-pop`（drawer / palette 浮层）。
两级封顶，不新增第三级。

## 项目绑定

token 落到具体文件，改动时按这张表对：

| 文件 | 视觉职责 |
|---|---|
| `web/src/styles.css` | token 唯一定义处。加色值只能加在这里。 |
| `web/src/components/Topbar.tsx` | 3px 圆角，`--bg-elevated` 底，mono 12px eyebrow |
| `web/src/components/Rail.tsx` | `--bg-rail` 底，选中态用 `accent`（交互色）不用橙 |
| `web/src/components/StatusPill.tsx` | 3px 圆角；`exit_code != 0` → danger，live → `#ee6018` |
| `web/src/components/CommandBlock.tsx` | mono，`--bg-inset` 底，命令原文不截断变形 |
| `web/src/components/DetailDrawer.tsx` | 20px 圆角，亮色用 `--shadow-pop` |
| `web/src/components/CommandPalette.tsx` | 20px 圆角，同上 |
| `web/src/components/primitives.tsx` | 按钮中性填充（`#1f1d1c` / `#fafafa`），禁品牌色 |
| `web/src/charts/DurationHistogram.tsx` | 柱体 `#4d4947`，超阈值柱 `#ee6018` |
| `web/src/charts/TrendChart.tsx` | 主笔画 `#ee6018`，改善趋势 `#a0ca92` |
| `web/src/charts/Heatmap.tsx` | 单色阶（灰→橙），不用彩虹色阶 |
| `web/src/charts/Sparkline.tsx` | 1px 笔画，无填充，无阴影 |
| `web/src/lib/theme.ts` | 主题切换逻辑，不含色值 |

## Do

- 每个区块都落在 `--bg` 上；只有卡片是亮的。
- 字重 400 打天下，标签必须压过周边时才 500。
- `#ee6018` 只出现在 live 状态和图表笔画。
- mono 12px 全大写做 eyebrow / 状态标签 / 列头。
- 深度靠对比和留白，暗色一个阴影都不加。
- 新增色值先问：它对应哪个可判定的数据事实？答不出就别加。

## Don't

- 不要给按钮填品牌色或语义色。
- 不要用 600+ 字重、不要加粗中文标题。
- 不要在图表里用第三个数据色，也不要彩虹色阶。
- 不要行高超过 1.5。
- 不要在暗色主题加阴影 / glow / blur / 渐变。
- 不要引第三个字族，不要引外部字体（会破 `file://`）。
- 不要为了「好看」把区块间距拉到 96px，这是数据面板不是落地页。

## 验收

改完前端，按顺序跑（命令已核实存在）：

```bash
cd ~/Documents/GitHub/cmdaudit/web
npm run typecheck        # tsc -b --noEmit
npm run build            # tsc -b && vite build
cd .. && scripts/sync-shell.sh   # 同步 src/cmdaudit/viz/shell.html，CI 会校验逐字节一致
```

视觉侧额外要求：

1. **对比度必须实测，不许推断。** 改了色值就在亮/暗双主题 × 六视图重采样文本对比度，
   目标 WCAG AA。方法参照 `docs/reviews/2026-08-26-frontend-audit.md` 的程序化采样口径
   （1440×900 / 720×900）。
2. `file://` 双击打开 `web/dist/index.html`，确认字体正常、无网络请求。
3. 圆角迁移做完后，全仓 grep 确认没有残留的 `12px` / `8px` 圆角字面量。

未做实测就不要在 PR 里写「对比度达标」。

