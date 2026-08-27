/**
 * 队列单行。信息优先级：状态 → 模板原文 → 失败次数/失败率 → 近期信号 → 维度。
 * 模板原文用 mono 且只截断不换行，保证上下行能对齐扫读。
 */
import { clsx } from "clsx";
import { motion } from "motion/react";
import { CheckSquareIcon, SquareIcon } from "@phosphor-icons/react";
import type { Finding } from "../lib/payload";
import type { TriageEntry } from "../lib/triage";
import { formatCount, formatPercent, formatRelative } from "../lib/format";
import { Badge, Meter } from "./primitives";
import { StatusDot } from "./StatusPill";
import { Sparkline } from "../charts/Sparkline";
import { LIST_ITEM } from "../lib/motion";

const KIND_TONE: Record<string, "danger" | "warn" | "accent" | "neutral"> = {
  network: "accent",
  timeout: "warn",
  not_found: "danger",
  build: "warn",
  test: "warn",
  permission: "danger",
};

export function FindingRow({
  finding,
  entry,
  maxFailures,
  selected,
  checked,
  latestEventAt,
  onOpen,
  onToggleCheck,
}: {
  finding: Finding;
  entry: TriageEntry;
  maxFailures: number;
  selected: boolean;
  checked: boolean;
  latestEventAt: string | null;
  onOpen: () => void;
  onToggleCheck: () => void;
}) {
  const kindTone = KIND_TONE[finding.failure_kind] ?? "neutral";
  return (
    <motion.li variants={LIST_ITEM} layout="position">
      <div
        role="button"
        tabIndex={-1}
        onClick={onOpen}
        data-selected={selected || undefined}
        className={clsx(
          "group grid cursor-pointer grid-cols-[22px_18px_minmax(0,1fr)_auto] items-center gap-x-3 border-b px-3 py-2.5 transition-colors duration-100",
          "hover:bg-[var(--bg-inset)] md:grid-cols-[22px_18px_minmax(0,1fr)_96px_78px_128px]",
        )}
        style={{
          borderColor: "var(--border)",
          background: selected ? "color-mix(in oklab, var(--color-accent-400) 8%, transparent)" : undefined,
          boxShadow: selected ? "inset 2px 0 0 var(--color-accent-400)" : undefined,
        }}
      >
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggleCheck();
          }}
          aria-label={checked ? "取消选中" : "选中"}
          className="grid h-5 w-5 place-items-center rounded-control transition-colors"
          style={{ color: checked ? "var(--text-accent)" : "var(--text-faint)" }}
        >
          {checked ? <CheckSquareIcon size={15} weight="fill" /> : <SquareIcon size={15} />}
        </button>

        <span className="grid h-4 w-4 place-items-center" title={entry.status}>
          <StatusDot status={entry.status} />
        </span>

        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <code className="clip flex-1 font-mono t-body" title={finding.template}>
              {finding.template || finding.program || finding.template_id}
            </code>
            <Badge tone={kindTone} mono>
              {finding.failure_kind}
            </Badge>
          </div>
          <p className="clip mt-1 t-label" style={{ color: "var(--text-faint)" }}>
            {finding.agents.join(" · ") || "—"}
            <span className="mx-1.5">/</span>
            {finding.projects.length > 2
              ? `${finding.projects.slice(0, 2).join(" · ")} +${finding.projects.length - 2}`
              : finding.projects.join(" · ") || "—"}
            <span className="mx-1.5">/</span>
            {formatRelative(finding.last_seen, latestEventAt)}
            {entry.owner ? (
              <>
                <span className="mx-1.5">/</span>
                <span style={{ color: "var(--text-accent)" }}>@{entry.owner}</span>
              </>
            ) : null}
          </p>
        </div>

        <div className="hidden md:block">
          <p className="num text-right t-body font-medium" style={{ color: "var(--text-danger)" }}>
            {formatCount(finding.failures)}
          </p>
          <div className="mt-1.5">
            <Meter ratio={maxFailures ? finding.failures / maxFailures : 0} />
          </div>
        </div>

        <p className="num hidden text-right t-body-sm md:block" style={{ color: "var(--text-muted)" }}>
          {formatPercent(finding.failures, finding.runs)}
          <span className="ml-1 t-label" style={{ color: "var(--text-faint)" }}>
            /{formatCount(finding.runs)}
          </span>
        </p>

        <div className="hidden justify-self-end opacity-80 transition-opacity group-hover:opacity-100 md:block">
          <Sparkline signal={finding.signal} />
        </div>

        <p className="num text-right t-mono font-medium md:hidden" style={{ color: "var(--text-danger)" }}>
          {formatCount(finding.failures)}
        </p>
      </div>
    </motion.li>
  );
}
