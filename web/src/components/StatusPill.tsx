/** 处理状态 pill + 就地切换。状态是人的判断，写在本机存储，不属于证据。 */
import { clsx } from "clsx";
import { STATUS_LABEL, TRIAGE_STATUSES, type TriageStatus } from "../lib/triage";
import type { BadgeTone } from "./primitives";

export const STATUS_TONE: Record<TriageStatus, BadgeTone> = {
  open: "danger",
  reviewing: "warn",
  verified: "ok",
  dismissed: "neutral",
};

const TONE_COLOR: Record<BadgeTone, string> = {
  neutral: "var(--text-faint)",
  accent: "var(--color-accent-500)",
  danger: "var(--color-danger-500)",
  warn: "var(--color-warn-400)",
  ok: "var(--color-ok-400)",
};

export function StatusDot({ status }: { status: TriageStatus }) {
  return (
    <span
      className="inline-block h-[7px] w-[7px] shrink-0 rounded-full"
      style={{ background: TONE_COLOR[STATUS_TONE[status]] }}
      aria-hidden
    />
  );
}

export function StatusPill({ status }: { status: TriageStatus }) {
  const color = TONE_COLOR[STATUS_TONE[status]];
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-1.5 py-[3px] text-[10.5px] font-medium leading-none"
      style={{
        color,
        borderColor: `color-mix(in oklab, ${color} 32%, transparent)`,
        background: `color-mix(in oklab, ${color} 12%, transparent)`,
      }}
    >
      <StatusDot status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}

/** 状态切换组。四态并列而非下拉：工作台里状态切换是高频动作，少一次点击。 */
export function StatusSwitch({
  value,
  onChange,
  size = "md",
}: {
  value: TriageStatus;
  onChange: (next: TriageStatus) => void;
  size?: "sm" | "md";
}) {
  return (
    <div
      role="group"
      aria-label="处理状态"
      className="inline-flex items-center gap-px overflow-hidden rounded-lg border p-px"
      style={{ borderColor: "var(--border)", background: "var(--bg-inset)" }}
    >
      {TRIAGE_STATUSES.map((status) => {
        const selected = status === value;
        const color = TONE_COLOR[STATUS_TONE[status]];
        return (
          <button
            key={status}
            type="button"
            onClick={() => onChange(status)}
            aria-pressed={selected}
            className={clsx(
              "rounded-[7px] font-medium transition-colors duration-150",
              size === "sm" ? "px-2 py-[3px] text-[10.5px]" : "px-2.5 py-1 text-[11.5px]",
            )}
            style={{
              color: selected ? color : "var(--text-faint)",
              background: selected ? "var(--bg-elevated)" : "transparent",
              boxShadow: selected ? "var(--shadow-card)" : "none",
            }}
          >
            {STATUS_LABEL[status]}
          </button>
        );
      })}
    </div>
  );
}
