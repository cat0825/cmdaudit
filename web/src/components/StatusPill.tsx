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

/* 这一份值同时当 pill 文字色和 StatusDot 的填充色，所以取**文字档**：
   文字要 4.5，圆点作为图形只要 3:1，取严的那档即可两用。
   实测：--color-danger-500 在暗/亮 pill 底上分别只有 3.32 / 3.73。 */
const TONE_COLOR: Record<BadgeTone, string> = {
  neutral: "var(--text-faint)",
  accent: "var(--text-accent)",
  danger: "var(--text-danger)",
  warn: "var(--text-warn)",
  ok: "var(--text-ok)",
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
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-control border px-1.5 py-[3px] t-label font-medium leading-none"
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
      className="inline-flex items-center gap-px overflow-hidden rounded-control border p-px"
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
              "rounded-control font-medium transition-colors duration-150",
              size === "sm" ? "px-2 py-[3px] t-label" : "px-2.5 py-1 t-body-sm",
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
