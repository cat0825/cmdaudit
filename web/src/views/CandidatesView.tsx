/**
 * 待验证候选。这些是**假设**不是结论，页面必须显式标 exploratory，
 * 并且把验证设计与 caveats 摊开 —— 否则读者会把优先级数字当成置信度。
 */
import { motion } from "motion/react";
import type { Payload } from "../lib/payload";
import { Badge, Card, Empty } from "../components/primitives";
import { LIST_CONTAINER, LIST_ITEM } from "../lib/motion";

export function CandidatesView({ payload }: { payload: Payload }) {
  return (
    <div className="grid gap-3">
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[13px] font-semibold tracking-tight">待验证候选</h2>
          <Badge tone="warn" mono>
            evidence_class = exploratory
          </Badge>
        </div>
        <p className="mt-2 max-w-[80ch] text-[11.5px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {payload.candidate_note ||
            "候选由筛选规则产出，只表示「值得做实验」，不表示已成立。优先级是排序权重，不是置信度。"}
        </p>
      </Card>

      <motion.ul variants={LIST_CONTAINER} initial="hidden" animate="visible" className="grid gap-3">
        {payload.candidates.map((candidate, index) => (
          <motion.li key={candidate.candidate_id || index} variants={LIST_ITEM}>
            <Card>
              <header className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge mono>{candidate.source_rule}</Badge>
                    <Badge mono>{candidate.candidate_id}</Badge>
                  </div>
                  <code className="mt-2 block break-all font-mono text-[12.5px] font-medium">
                    {candidate.command_shape}
                  </code>
                </div>
                <div className="text-right">
                  <p className="font-mono text-[9.5px] uppercase" style={{ color: "var(--text-faint)" }}>
                    优先级
                  </p>
                  <p className="num text-[15px] font-semibold" style={{ color: "var(--color-warn-400)" }}>
                    {candidate.priority.toFixed(2)}
                  </p>
                </div>
              </header>

              <div className="mt-3 grid gap-2.5 lg:grid-cols-2">
                <div>
                  <p className="font-mono text-[9.5px] uppercase" style={{ color: "var(--text-faint)" }}>
                    假设
                  </p>
                  <p className="mt-1 text-[11.5px] leading-relaxed">{candidate.hypothesis}</p>
                </div>
                <div>
                  <p className="font-mono text-[9.5px] uppercase" style={{ color: "var(--text-faint)" }}>
                    验证设计
                  </p>
                  <p className="mt-1 text-[11.5px] leading-relaxed">{candidate.design || "—"}</p>
                </div>
              </div>

              {Object.keys(candidate.observed).length > 0 ? (
                <dl
                  className="mt-3 grid gap-px overflow-hidden rounded-lg sm:grid-cols-3 lg:grid-cols-4"
                  style={{ background: "var(--border)" }}
                >
                  {Object.entries(candidate.observed).map(([label, value]) => (
                    <div key={label} className="px-2.5 py-2" style={{ background: "var(--bg-inset)" }}>
                      <dt className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                        {label}
                      </dt>
                      <dd className="num mt-0.5 text-[12px] font-medium">
                        {typeof value === "number"
                          ? value.toLocaleString("en-US")
                          : String(value ?? "—")}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : null}

              {candidate.caveats.length > 0 ? (
                <ul className="mt-3 grid gap-1">
                  {candidate.caveats.map((caveat) => (
                    <li
                      key={caveat}
                      className="border-l-2 pl-2.5 text-[11px] leading-relaxed"
                      style={{ borderColor: "var(--color-warn-400)", color: "var(--text-muted)" }}
                    >
                      {caveat}
                    </li>
                  ))}
                </ul>
              ) : null}
            </Card>
          </motion.li>
        ))}
      </motion.ul>

      {payload.candidates.length === 0 ? (
        <Card>
          <Empty title="候选队列为空" hint="运行 cmdaudit screen 生成 candidates.json 后重新生成页面。" />
        </Card>
      ) : null}
    </div>
  );
}
