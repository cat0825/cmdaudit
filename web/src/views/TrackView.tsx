/**
 * 轨道视图：直接复用 Python 侧已算好的 Section/Row 结构。
 *
 * 口径声明（scope_name + caveat）必须原样出现在页面上 —— 这是这个项目的硬约束，
 * 把口径藏进 tooltip 等于允许读者跨口径比较。
 */
import { useState } from "react";
import { motion } from "motion/react";
import { CaretRightIcon } from "@phosphor-icons/react";
import type { Payload, Row, Section, Track } from "../lib/payload";
import { Badge, Card, Empty, Meter } from "../components/primitives";
import { CommandBlock } from "../components/CommandBlock";
import { DurationHistogram } from "../charts/DurationHistogram";
import { formatSeconds } from "../lib/format";
import { LIST_CONTAINER, LIST_ITEM } from "../lib/motion";

function cellText(value: string | number | null): string {
  if (value === null) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString("en-US") : value.toFixed(2);
  return value;
}

function RowItem({
  row,
  section,
  tone,
}: {
  row: Row;
  section: Section;
  tone: "danger" | "accent";
}) {
  const [open, setOpen] = useState(false);
  const barIndex = section.bar_column ? section.columns.indexOf(section.bar_column) : -1;

  return (
    <motion.li variants={LIST_ITEM} className="border-b last:border-b-0" style={{ borderColor: "var(--border)" }}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="grid w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-[var(--bg-inset)]"
        style={{ gridTemplateColumns: `18px minmax(0,1fr) repeat(${Math.max(0, section.columns.length - 1)}, minmax(60px, 96px))` }}
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.14 }} className="grid place-items-center">
          <CaretRightIcon size={11} style={{ color: "var(--text-faint)" }} />
        </motion.span>
        <span className="min-w-0">
          <code className="clip block font-mono text-[12px]" title={cellText(row.cells[0] ?? null)}>
            {cellText(row.cells[0] ?? null)}
          </code>
          {barIndex > 0 ? (
            <span className="mt-1.5 block max-w-[320px]">
              <Meter ratio={row.bar_ratio} tone={tone} />
            </span>
          ) : null}
        </span>
        {section.columns.slice(1).map((column, index) => (
          <span
            key={column}
            className="num text-right text-[11.5px]"
            style={{ color: index === barIndex - 1 ? `var(--color-${tone === "danger" ? "danger-500" : "accent-500"})` : "var(--text-muted)" }}
          >
            {cellText(row.cells[index + 1] ?? null)}
          </span>
        ))}
      </button>

      {open ? (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="overflow-hidden px-4 pb-3.5"
          style={{ background: "var(--bg-inset)" }}
        >
          <ul className="grid gap-2 pt-3">
            {row.samples.map((sample, index) => (
              <li
                key={`${sample.command}-${index}`}
                className="rounded-lg border p-2.5"
                style={{ borderColor: "var(--border)", background: "var(--bg-elevated)" }}
              >
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge mono>{sample.agent}</Badge>
                  <Badge mono>{sample.project}</Badge>
                  <Badge tone={sample.status === "failed" ? "danger" : "ok"} mono>
                    {sample.status} / exit {sample.exit_code ?? "—"}
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
          {row.drill_sql ? (
            <div className="mt-2.5">
              <CommandBlock text={row.drill_sql} label="可复现 SQL" wrap />
            </div>
          ) : null}
        </motion.div>
      ) : null}
    </motion.li>
  );
}

function TrackBlock({ track }: { track: Track }) {
  const tone = track.tone === "failure" ? "danger" : "accent";
  return (
    <div className="grid gap-3">
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[14px] font-semibold tracking-tight">{track.title}</h2>
          <Badge tone={tone} mono>
            口径 {track.scope_name}
          </Badge>
        </div>
        <p className="mt-2 max-w-[80ch] text-[11.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {track.lead}
        </p>
        <p
          className="mt-2 border-l-2 pl-2.5 text-[11px] leading-relaxed"
          style={{ borderColor: `var(--color-${tone === "danger" ? "danger-500" : "accent-500"})`, color: "var(--text-muted)" }}
        >
          {track.caveat}
        </p>
      </Card>

      {track.sections.map((section) => (
        <Card key={section.key} padded={false}>
          <header className="border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
            <h3 className="text-[12.5px] font-semibold">{section.title}</h3>
            {section.note ? (
              <p className="mt-1 max-w-[86ch] text-[10.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {section.note}
              </p>
            ) : null}
          </header>
          <div
            className="grid items-center gap-3 border-b px-4 py-1.5 text-[9.5px] uppercase tracking-wide"
            style={{
              gridTemplateColumns: `18px minmax(0,1fr) repeat(${Math.max(0, section.columns.length - 1)}, minmax(60px, 96px))`,
              borderColor: "var(--border)",
              color: "var(--text-faint)",
              background: "var(--bg-inset)",
            }}
          >
            <span />
            <span>{section.columns[0]}</span>
            {section.columns.slice(1).map((column) => (
              <span key={column} className="text-right">
                {column}
              </span>
            ))}
          </div>
          <motion.ul variants={LIST_CONTAINER} initial="hidden" animate="visible">
            {section.rows.map((row, index) => (
              <RowItem key={`${section.key}-${index}`} row={row} section={section} tone={tone} />
            ))}
          </motion.ul>
          {section.rows.length === 0 ? <Empty title="这张表没有数据" /> : null}
          <div className="px-4 py-3">
            <CommandBlock text={section.sql} label="聚合 SQL" wrap />
          </div>
        </Card>
      ))}
    </div>
  );
}

export function DurationView({ payload }: { payload: Payload }) {
  const track = payload.tracks.find((item) => item.key === "duration");
  const profile = payload.dashboard.duration_profile;
  return (
    <div className="grid gap-4">
      {profile ? (
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-[13px] font-semibold tracking-tight">耗时分布</h2>
              <p className="mt-1 max-w-[76ch] text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                桶宽不等距，每桶等宽显示，x 轴标注真实区间。超过 p90 的桶用琥珀色标出 —— 那才是值得优化的部分。
              </p>
            </div>
            <Badge tone="accent" mono>
              样本 {profile.sample_size.toLocaleString("en-US")} 条
            </Badge>
          </div>
          <div className="mt-3">
            <DurationHistogram profile={profile} />
          </div>
        </Card>
      ) : null}
      {track ? <TrackBlock track={track} /> : <Empty title="没有耗时轨道数据" />}
    </div>
  );
}

export function EvidenceView({ payload }: { payload: Payload }) {
  const failureTrack = payload.tracks.find((item) => item.key === "failure");
  return (
    <div className="grid gap-4">
      <Card>
        <h2 className="text-[13px] font-semibold tracking-tight">覆盖度</h2>
        <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
          每个排除项都能解释去向。分母不同的数字不可相加。
        </p>
        <dl
          className="mt-3 grid gap-px overflow-hidden rounded-lg sm:grid-cols-2 lg:grid-cols-4"
          style={{ background: "var(--border)" }}
        >
          {Object.entries(payload.coverage).map(([label, value]) => (
            <div key={label} className="px-3 py-2.5" style={{ background: "var(--bg-elevated)" }}>
              <dt className="text-[10.5px]" style={{ color: "var(--text-muted)" }}>
                {label}
              </dt>
              <dd className="num mt-1 text-[13.5px] font-semibold">
                {typeof value === "number" ? value.toLocaleString("en-US") : (value ?? "—")}
              </dd>
            </div>
          ))}
        </dl>
      </Card>
      {failureTrack ? <TrackBlock track={failureTrack} /> : null}
      {payload.warnings.length > 0 ? (
        <Card>
          <h2 className="text-[13px] font-semibold tracking-tight">生成告警</h2>
          <ul className="mt-2 grid gap-1.5">
            {payload.warnings.map((warning) => (
              <li key={warning} className="text-[11.5px] leading-relaxed" style={{ color: "var(--color-warn-400)" }}>
                {warning}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
