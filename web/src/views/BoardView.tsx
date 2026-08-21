/**
 * 处理看板。按本机处理状态分四列。
 * 不做拖拽：拖拽在 100+ 卡片的列里容易误操作，且键盘用户无法使用。
 * 改状态走卡片上的 1/2/3/4 快捷键与状态条，语义更明确。
 */
import { useMemo } from "react";
import { motion } from "motion/react";
import type { Payload } from "../lib/payload";
import { Badge, Empty } from "../components/primitives";
import { Sparkline } from "../charts/Sparkline";
import { STATUS_LABEL, TRIAGE_STATUSES, entryFor, type TriageMap, type TriageStatus } from "../lib/triage";
import { STATUS_TONE, StatusDot } from "../components/StatusPill";
import { formatCount, formatPercent } from "../lib/format";
import { LIST_CONTAINER, LIST_ITEM } from "../lib/motion";

const TONE_COLOR: Record<string, string> = {
  neutral: "var(--text-faint)",
  accent: "var(--color-accent-500)",
  danger: "var(--color-danger-500)",
  warn: "var(--color-warn-400)",
  ok: "var(--color-ok-400)",
};

export function BoardView({
  payload,
  triage,
  onOpen,
  onSetStatus,
}: {
  payload: Payload;
  triage: TriageMap;
  onOpen: (findingId: string) => void;
  onSetStatus: (findingId: string, status: TriageStatus) => void;
}) {
  const columns = useMemo(() => {
    const buckets = new Map<TriageStatus, typeof payload.findings>();
    for (const status of TRIAGE_STATUSES) buckets.set(status, []);
    for (const finding of payload.findings) {
      const status = entryFor(triage, finding.finding_id).status;
      buckets.get(status)!.push(finding);
    }
    for (const list of buckets.values()) list.sort((a, b) => b.failures - a.failures);
    return buckets;
  }, [payload.findings, triage]);

  return (
    <div className="grid gap-3 lg:grid-cols-4">
      {TRIAGE_STATUSES.map((status) => {
        const items = columns.get(status) ?? [];
        const color = TONE_COLOR[STATUS_TONE[status]]!;
        return (
          <section
            key={status}
            className="flex min-h-[220px] flex-col rounded-card border"
            style={{ borderColor: "var(--border)", background: "var(--bg-inset)" }}
          >
            <header
              className="flex items-center gap-2 border-b px-3 py-2.5"
              style={{ borderColor: "var(--border)" }}
            >
              <StatusDot status={status} />
              <h2 className="text-[12px] font-semibold">{STATUS_LABEL[status]}</h2>
              <span className="num ml-auto text-[11px]" style={{ color: "var(--text-faint)" }}>
                {formatCount(items.length)}
              </span>
            </header>

            <motion.ul
              variants={LIST_CONTAINER}
              initial="hidden"
              animate="visible"
              className="flex-1 overflow-y-auto p-2"
              style={{ maxHeight: "calc(100vh - 240px)" }}
            >
              {items.map((finding) => (
                <motion.li key={finding.finding_id} variants={LIST_ITEM} layout="position" className="mb-2 last:mb-0">
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => onOpen(finding.finding_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onOpen(finding.finding_id);
                      }
                      const slot = Number.parseInt(event.key, 10);
                      if (slot >= 1 && slot <= TRIAGE_STATUSES.length) {
                        event.preventDefault();
                        onSetStatus(finding.finding_id, TRIAGE_STATUSES[slot - 1]!);
                      }
                    }}
                    className="cursor-pointer rounded-lg border p-2.5 transition-shadow hover:shadow-[var(--shadow-card)]"
                    style={{
                      background: "var(--bg-elevated)",
                      borderColor: "var(--border)",
                      borderLeft: `2px solid ${color}`,
                    }}
                  >
                    <code className="clip block font-mono text-[11.5px]" title={finding.template}>
                      {finding.template}
                    </code>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <Badge tone="danger" mono>
                        {finding.failure_kind}
                      </Badge>
                      <span className="num text-[11px] font-semibold" style={{ color: "var(--color-danger-500)" }}>
                        {formatCount(finding.failures)}
                        <span className="ml-1 text-[9.5px] font-normal" style={{ color: "var(--text-faint)" }}>
                          {formatPercent(finding.failures, finding.runs)}
                        </span>
                      </span>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="clip text-[10px]" style={{ color: "var(--text-faint)" }}>
                        {finding.agents.join(" · ")}
                      </span>
                      <Sparkline signal={finding.signal} />
                    </div>
                  </div>
                </motion.li>
              ))}
            </motion.ul>

            {items.length === 0 ? (
              <Empty
                title="这一列是空的"
                hint={status === "open" ? "所有模式都已分流。" : "把队列里的模式切到这个状态后会出现在这里。"}
              />
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
