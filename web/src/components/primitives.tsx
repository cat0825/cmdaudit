/** 基础展示件。只做样式与语义，不含业务判断。 */
import { clsx } from "clsx";
import type { ReactNode } from "react";

export function Card({
  className,
  children,
  padded = true,
}: {
  className?: string;
  children: ReactNode;
  padded?: boolean;
}) {
  return (
    <section className={clsx("surface", padded && "p-5", className)}>{children}</section>
  );
}

export function CardHead({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
        {hint ? (
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {hint}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

const TONE_STYLE: Record<string, { color: string; bg: string; border: string }> = {
  neutral: { color: "var(--text-muted)", bg: "var(--bg-inset)", border: "var(--border)" },
  accent: {
    color: "var(--color-accent-500)",
    bg: "color-mix(in oklab, var(--color-accent-400) 12%, transparent)",
    border: "color-mix(in oklab, var(--color-accent-400) 32%, transparent)",
  },
  danger: {
    color: "var(--color-danger-500)",
    bg: "color-mix(in oklab, var(--color-danger-400) 14%, transparent)",
    border: "color-mix(in oklab, var(--color-danger-400) 34%, transparent)",
  },
  warn: {
    color: "var(--color-warn-400)",
    bg: "color-mix(in oklab, var(--color-warn-400) 16%, transparent)",
    border: "color-mix(in oklab, var(--color-warn-400) 36%, transparent)",
  },
  ok: {
    color: "var(--color-ok-400)",
    bg: "color-mix(in oklab, var(--color-ok-400) 14%, transparent)",
    border: "color-mix(in oklab, var(--color-ok-400) 34%, transparent)",
  },
};

export type BadgeTone = keyof typeof TONE_STYLE;

export function Badge({
  children,
  tone = "neutral",
  mono = false,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  mono?: boolean;
  className?: string;
}) {
  const style = TONE_STYLE[tone] ?? TONE_STYLE.neutral!;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium leading-none",
        mono && "font-mono",
        className,
      )}
      style={{ color: style.color, background: style.bg, borderColor: style.border }}
    >
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd
      className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border px-1 font-mono text-[10px] leading-none"
      style={{ color: "var(--text-faint)", borderColor: "var(--border)", background: "var(--bg-inset)" }}
    >
      {children}
    </kbd>
  );
}

/** 空状态。工作台里空状态必须说明「为什么空」，不能只画个图标。 */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-6 py-12 text-center">
      <p className="text-[13px] font-medium">{title}</p>
      {hint ? (
        <p className="max-w-[42ch] text-[11.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function Meter({ ratio, tone = "danger" }: { ratio: number; tone?: BadgeTone }) {
  const style = TONE_STYLE[tone] ?? TONE_STYLE.neutral!;
  const width = `${Math.max(2, Math.min(100, ratio * 100))}%`;
  return (
    <span
      className="block h-1 w-full overflow-hidden rounded-full"
      style={{ background: style.bg }}
      aria-hidden
    >
      <span className="block h-full rounded-full" style={{ width, background: style.color }} />
    </span>
  );
}
