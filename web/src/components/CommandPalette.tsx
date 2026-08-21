/**
 * ⌘K 命令面板。三类条目：跳转视图、切主题、按 finding 搜索并直接打开详情。
 * 匹配用简单子串（大小写无关）而非模糊算法：命令模板本身就是精确文本，
 * 模糊匹配在这里只会把噪声排到前面。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Finding } from "../lib/payload";
import { VIEWS, type ViewId } from "../lib/views";
import { Badge, Kbd } from "./primitives";
import { EASE_FAST, SPRING_POP } from "../lib/motion";
import { formatCount } from "../lib/format";
import type { ThemeChoice } from "../lib/theme";

interface Action {
  id: string;
  label: string;
  hint: string;
  group: string;
  badge?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  findings,
  onNavigate,
  onOpenFinding,
  onThemeChange,
}: {
  open: boolean;
  onClose: () => void;
  findings: Finding[];
  onNavigate: (view: ViewId) => void;
  onOpenFinding: (findingId: string) => void;
  onThemeChange: (choice: ThemeChoice) => void;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      // 等入场动画的第一帧过去再聚焦，否则 Safari 会把滚动位置带跑。
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const actions = useMemo<Action[]>(() => {
    const navigation: Action[] = VIEWS.map((view) => ({
      id: `view:${view.id}`,
      label: view.label,
      hint: view.hint,
      group: "跳转",
      run: () => onNavigate(view.id),
    }));
    const themes: Action[] = (
      [
        ["system", "主题：跟随系统"],
        ["light", "主题：浅色"],
        ["dark", "主题：深色"],
      ] as const
    ).map(([choice, label]) => ({
      id: `theme:${choice}`,
      label,
      hint: "切换外观",
      group: "外观",
      run: () => onThemeChange(choice),
    }));
    const items: Action[] = findings.slice(0, 400).map((finding) => ({
      id: `finding:${finding.finding_id}`,
      label: finding.template || finding.template_id,
      hint: `${finding.program || "—"} · ${finding.agents.join(" ") || "—"}`,
      group: "失败模式",
      badge: `${formatCount(finding.failures)} 次 · ${finding.failure_kind}`,
      run: () => onOpenFinding(finding.finding_id),
    }));
    return [...navigation, ...themes, ...items];
  }, [findings, onNavigate, onOpenFinding, onThemeChange]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return actions.filter((action) => action.group !== "失败模式").slice(0, 12);
    return actions
      .filter(
        (action) =>
          action.label.toLowerCase().includes(needle) ||
          action.hint.toLowerCase().includes(needle) ||
          (action.badge?.toLowerCase().includes(needle) ?? false),
      )
      .slice(0, 40);
  }, [actions, query]);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  useEffect(() => {
    // 键盘移动光标时把选中项滚进视野，避免光标跑到不可见区域。
    listRef.current?.children[cursor]?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!open) return null;

  const commit = (action: Action | undefined) => {
    if (!action) return;
    action.run();
    onClose();
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 grid place-items-start justify-center pt-[12vh]"
        style={{ background: "oklch(0.15 0.01 265 / 0.4)", backdropFilter: "blur(4px)" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={EASE_FAST}
        onClick={onClose}
      >
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="命令面板"
          className="w-[min(620px,calc(100vw-32px))] overflow-hidden rounded-xl border"
          style={{ background: "var(--bg-elevated)", borderColor: "var(--border-strong)", boxShadow: "var(--shadow-pop)" }}
          initial={{ opacity: 0, scale: 0.97, y: -8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.98, y: -4 }}
          transition={SPRING_POP}
          onClick={(event) => event.stopPropagation()}
        >
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" || (event.key === "n" && event.ctrlKey)) {
                event.preventDefault();
                setCursor((current) => Math.min(results.length - 1, current + 1));
              } else if (event.key === "ArrowUp" || (event.key === "p" && event.ctrlKey)) {
                event.preventDefault();
                setCursor((current) => Math.max(0, current - 1));
              } else if (event.key === "Enter") {
                event.preventDefault();
                commit(results[cursor]);
              } else if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              }
            }}
            placeholder="搜索命令模板、失败类型，或跳转视图…"
            className="w-full border-b bg-transparent px-4 py-3.5 text-[13.5px] outline-none"
            style={{ borderColor: "var(--border)", color: "var(--text)" }}
          />
          <ul ref={listRef} className="max-h-[52vh] overflow-y-auto p-1.5">
            {results.length === 0 ? (
              <li className="px-3 py-6 text-center text-[12px]" style={{ color: "var(--text-faint)" }}>
                没有匹配项
              </li>
            ) : (
              results.map((action, index) => (
                <li key={action.id}>
                  <button
                    type="button"
                    onClick={() => commit(action)}
                    onMouseEnter={() => setCursor(index)}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors"
                    style={{ background: index === cursor ? "var(--bg-inset)" : "transparent" }}
                  >
                    <span
                      className="w-[52px] shrink-0 text-[9.5px] uppercase tracking-wide"
                      style={{ color: "var(--text-faint)" }}
                    >
                      {action.group}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="clip block font-mono text-[12px]">{action.label}</span>
                      <span className="clip block text-[10.5px]" style={{ color: "var(--text-faint)" }}>
                        {action.hint}
                      </span>
                    </span>
                    {action.badge ? (
                      <Badge tone="danger" mono>
                        {action.badge}
                      </Badge>
                    ) : null}
                  </button>
                </li>
              ))
            )}
          </ul>
          <footer
            className="flex items-center gap-3 border-t px-3.5 py-2 text-[10px]"
            style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}
          >
            <span className="flex items-center gap-1">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> 选择
            </span>
            <span className="flex items-center gap-1">
              <Kbd>↵</Kbd> 执行
            </span>
            <span className="flex items-center gap-1">
              <Kbd>Esc</Kbd> 关闭
            </span>
          </footer>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
