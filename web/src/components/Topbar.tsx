/** 顶栏：位置 + 数据新鲜度 + 主题 + ⌘K 入口。 */
import { MagnifyingGlassIcon, MonitorIcon, MoonIcon, SunIcon } from "@phosphor-icons/react";
import { Kbd } from "./primitives";
import type { ThemeChoice } from "../lib/theme";
import { VIEWS, type ViewId } from "../lib/views";

const THEME_ORDER: ThemeChoice[] = ["system", "light", "dark"];
const THEME_LABEL: Record<ThemeChoice, string> = {
  system: "跟随系统",
  light: "浅色",
  dark: "深色",
};

export function Topbar({
  view,
  generatedAt,
  latestEventAt,
  themeChoice,
  onThemeChange,
  onOpenPalette,
}: {
  view: ViewId;
  generatedAt: string;
  latestEventAt: string | null;
  themeChoice: ThemeChoice;
  onThemeChange: (next: ThemeChoice) => void;
  onOpenPalette: () => void;
}) {
  const meta = VIEWS.find((item) => item.id === view);
  const ThemeIcon = themeChoice === "light" ? SunIcon : themeChoice === "dark" ? MoonIcon : MonitorIcon;

  return (
    <header
      className="sticky top-0 z-20 flex h-[60px] items-center justify-between gap-4 border-b px-6"
      style={{
        borderColor: "var(--border)",
        /* 不透明。原来是 88% 半透明 + blur(10px)：DESIGN.md 明令「不要 blur」，
           而且滚动时内容会透上来，标题栏文字的对比度就不再是可保证的定值。
           分层靠下边框那 1px --border，不靠玻璃感。 */
        background: "var(--bg)",
      }}
    >
      <div className="min-w-0">
        <h1 className="truncate t-title font-medium">{meta?.label ?? "总览"}</h1>
        <p className="clip t-label" style={{ color: "var(--text-muted)" }}>
          {meta?.hint}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <div className="hidden text-right md:block">
          <p className="t-eyebrow-cjk" style={{ color: "var(--text-faint)" }}>
            最新事件
          </p>
          <p className="num t-label" style={{ color: "var(--text-muted)" }}>
            {latestEventAt ? latestEventAt.slice(0, 16).replace("T", " ") : "—"}
          </p>
        </div>

        <span className="hidden h-6 w-px lg:block" style={{ background: "var(--border)" }} />

        <p className="num hidden t-label lg:block" style={{ color: "var(--text-faint)" }}>
          生成于 {generatedAt}
        </p>

        <button
          type="button"
          onClick={() => {
            const index = THEME_ORDER.indexOf(themeChoice);
            onThemeChange(THEME_ORDER[(index + 1) % THEME_ORDER.length]!);
          }}
          title={`主题：${THEME_LABEL[themeChoice]}（点击切换）`}
          aria-label={`主题：${THEME_LABEL[themeChoice]}`}
          className="grid h-[30px] w-[30px] place-items-center rounded-control border transition-colors hover:bg-[var(--bg-inset)]"
          style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
        >
          <ThemeIcon size={15} />
        </button>

        <button
          type="button"
          onClick={onOpenPalette}
          className="flex h-[30px] items-center gap-2 rounded-control border pl-2.5 pr-2 t-body-sm transition-colors hover:bg-[var(--bg-inset)]"
          style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
        >
          <MagnifyingGlassIcon size={13} />
          <span className="hidden sm:inline">搜索与操作</span>
          <Kbd>⌘K</Kbd>
        </button>
      </div>
    </header>
  );
}
