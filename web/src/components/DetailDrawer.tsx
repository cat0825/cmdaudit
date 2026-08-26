/**
 * 失败模式详情抽屉。
 *
 * 上半是**人的判断**（状态 / 负责人 / 备注，写本机存储），
 * 下半是**证据**（命令原文、错误片段、可复现 SQL，只读）。
 * 两者用分隔与标签明确切开，避免读者把备注当成数据。
 */
import { AnimatePresence, motion } from "motion/react";
import { XIcon } from "@phosphor-icons/react";
import type { Finding } from "../lib/payload";
import type { TriageEntry, TriageStatus } from "../lib/triage";
import { formatCount, formatMonthDay, formatPercent, formatSeconds } from "../lib/format";
import { Badge, Kbd } from "./primitives";
import { StatusSwitch } from "./StatusPill";
import { CommandBlock } from "./CommandBlock";
import { EASE_FAST, SPRING_DRAWER } from "../lib/motion";

export function DetailDrawer({
  finding,
  entry,
  jumpEnabled,
  onClose,
  onPatch,
}: {
  finding: Finding | null;
  entry: TriageEntry;
  jumpEnabled: boolean;
  onClose: () => void;
  onPatch: (patch: Partial<TriageEntry>) => void;
}) {
  return (
    <AnimatePresence>
      {finding ? (
        <>
          <motion.div
            key="scrim"
            className="fixed inset-0 z-30"
            style={{ background: "oklch(0.15 0.01 265 / 0.32)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={EASE_FAST}
            onClick={onClose}
          />
          <motion.aside
            key="drawer"
            aria-label="失败模式详情"
            className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l sm:w-[min(560px,92vw)]"
            style={{ background: "var(--bg-elevated)", borderColor: "var(--border)", boxShadow: "var(--shadow-pop)" }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={SPRING_DRAWER}
          >
            <header
              className="flex items-start justify-between gap-3 border-b px-5 py-4"
              style={{ borderColor: "var(--border)" }}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="danger" mono>
                    {finding.failure_kind}
                  </Badge>
                  <Badge mono>{finding.program || "—"}</Badge>
                  <Badge mono>{finding.template_id}</Badge>
                </div>
                <code className="mt-2 block break-all font-mono text-[13px] font-medium">
                  {finding.template}
                </code>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭"
                className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border transition-colors hover:bg-[var(--bg-inset)]"
                style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
              >
                <XIcon size={13} />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto">
              <dl
                className="grid grid-cols-4 gap-px"
                style={{ background: "var(--border)" }}
              >
                {(
                  [
                    ["失败次数", formatCount(finding.failures), "var(--color-danger-500)"],
                    ["执行总数", formatCount(finding.runs), undefined],
                    ["失败率", formatPercent(finding.failures, finding.runs), undefined],
                    [
                      "首次 / 末次",
                      `${formatMonthDay(finding.first_seen)} → ${formatMonthDay(finding.last_seen)}`,
                      undefined,
                    ],
                  ] as const
                ).map(([label, value, color]) => (
                  <div key={label} className="px-3 py-2.5" style={{ background: "var(--bg-elevated)" }}>
                    <dt className="text-[9.5px]" style={{ color: "var(--text-faint)" }}>
                      {label}
                    </dt>
                    <dd className="num mt-1 text-[13px] font-semibold" style={{ color }}>
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>

              {/* 人的判断区 */}
              <section className="border-b px-5 py-4" style={{ borderColor: "var(--border)" }}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-[12px] font-semibold">处理状态</h3>
                  <p className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                    存本机浏览器，不写入数据库
                  </p>
                </div>
                <div className="mt-2.5">
                  <StatusSwitch
                    value={entry.status}
                    onChange={(next: TriageStatus) => onPatch({ status: next })}
                  />
                </div>
                <div className="mt-3 grid gap-2.5">
                  <label className="grid gap-1">
                    <span className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                      负责人
                    </span>
                    <input
                      value={entry.owner}
                      onChange={(event) => onPatch({ owner: event.target.value })}
                      placeholder="谁在跟这条"
                      className="rounded-lg border px-2.5 py-1.5 text-[12px] outline-none transition-colors focus:border-[var(--color-accent-400)]"
                      style={{ background: "var(--bg-inset)", borderColor: "var(--border)", color: "var(--text)" }}
                    />
                  </label>
                  <label className="grid gap-1">
                    <span className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                      结论 / 反事实实验记录
                    </span>
                    <textarea
                      value={entry.note}
                      onChange={(event) => onPatch({ note: event.target.value })}
                      rows={3}
                      placeholder="改了什么、有没有复现、下一步验证怎么设计"
                      className="resize-y rounded-lg border px-2.5 py-1.5 text-[12px] leading-relaxed outline-none transition-colors focus:border-[var(--color-accent-400)]"
                      style={{ background: "var(--bg-inset)", borderColor: "var(--border)", color: "var(--text)" }}
                    />
                  </label>
                  {entry.updated_at ? (
                    <p className="num text-[10px]" style={{ color: "var(--text-faint)" }}>
                      更新于 {entry.updated_at.slice(0, 16).replace("T", " ")}
                    </p>
                  ) : null}
                </div>
              </section>

              {/* 证据区 */}
              <section className="px-5 py-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-[12px] font-semibold">命令原文样本</h3>
                  <p className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                    最近 {finding.samples.length} 条，来自 commands 表
                  </p>
                </div>
                <ul className="mt-2.5 grid gap-2.5">
                  {finding.samples.map((sample, index) => (
                    <li
                      key={`${sample.command}-${index}`}
                      className="rounded-lg border p-2.5"
                      style={{ borderColor: "var(--border)", background: "var(--bg)" }}
                    >
                      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                        <Badge mono>{sample.agent}</Badge>
                        <Badge mono>{sample.project}</Badge>
                        <Badge tone="danger" mono>
                          exit {sample.exit_code ?? "—"}
                        </Badge>
                        <Badge mono>{formatSeconds(sample.duration_s)}</Badge>
                        <Badge mono>{sample.duration_source}</Badge>
                      </div>
                      <CommandBlock text={sample.command} wrap />
                      {sample.error_snippet ? (
                        <div className="mt-2">
                          <CommandBlock text={sample.error_snippet} label="错误片段" wrap />
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>

                <div className="mt-4">
                  <CommandBlock text={finding.drill_sql} label="可复现 SQL" wrap />
                </div>
              </section>
            </div>

            <footer
              className="flex items-center justify-between gap-3 border-t px-5 py-2.5 text-[10.5px]"
              style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}
            >
              {jumpEnabled ? (
                <span className="flex items-center gap-1.5">
                  <Kbd>J</Kbd>
                  <Kbd>K</Kbd> 上下条
                </span>
              ) : (
                <span />
              )}
              <span className="flex items-center gap-1.5">
                <Kbd>Esc</Kbd> 关闭
              </span>
            </footer>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}
