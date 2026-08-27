/**
 * agent × 自然日 失败热力图。
 *
 * 两种「没有颜色」必须能区分：
 * - 该 agent 当天**没跑过**命令 → 空槽（虚线描边，无填充）；
 * - 跑了但**零失败** → 最浅一档实色。
 * 补零会把前者伪装成后者，那是最容易误导人的一种图。
 */
import { memo, useMemo, useState } from "react";
import { motion } from "motion/react";
import type { HeatCell } from "../lib/payload";
import { formatCount, formatPercent } from "../lib/format";

interface Slot {
  agent: string;
  day: string;
  cell: HeatCell | null;
}

export const Heatmap = memo(function Heatmap({
  agents,
  days,
  cells,
}: {
  agents: string[];
  days: string[];
  cells: HeatCell[];
}) {
  const [hover, setHover] = useState<Slot | null>(null);

  const { grid, maxFailures } = useMemo(() => {
    const index = new Map<string, HeatCell>();
    let max = 0;
    for (const cell of cells) {
      index.set(`${cell.agent}|${cell.day}`, cell);
      if (cell.failures > max) max = cell.failures;
    }
    const rows: Slot[][] = agents.map((agent) =>
      days.map((day) => ({ agent, day, cell: index.get(`${agent}|${day}`) ?? null })),
    );
    return { grid: rows, maxFailures: max };
  }, [agents, days, cells]);

  // 分档而非连续插值：连续色阶在小方格上人眼分辨不出来，分档能直接读出量级。
  const level = (failures: number): number => {
    if (failures <= 0) return 0;
    if (!maxFailures) return 1;
    const ratio = failures / maxFailures;
    if (ratio <= 0.08) return 1;
    if (ratio <= 0.22) return 2;
    if (ratio <= 0.5) return 3;
    return 4;
  };

  const LEVEL_ALPHA = [0.06, 0.22, 0.42, 0.68, 1];

  return (
    <div className="relative">
      <div className="overflow-x-auto pb-1">
        <div className="inline-grid gap-[3px]" style={{ gridTemplateColumns: `76px repeat(${days.length}, 13px)` }}>
          {grid.map((row, rowIndex) => (
            <div key={agents[rowIndex]} className="contents">
              <span
                className="clip self-center pr-2 font-mono t-eyebrow-cjk"
                style={{ color: "var(--text-muted)" }}
                title={agents[rowIndex]}
              >
                {agents[rowIndex]}
              </span>
              {row.map((slot, colIndex) => {
                if (!slot.cell) {
                  return (
                    <span
                      key={slot.day}
                      className="h-[13px] w-[13px] rounded-[3px] border border-dashed"
                      style={{ borderColor: "var(--border)" }}
                      title={`${slot.agent} · ${slot.day} · 未运行`}
                    />
                  );
                }
                const lvl = level(slot.cell.failures);
                return (
                  <motion.span
                    key={slot.day}
                    className="h-[13px] w-[13px] cursor-default rounded-[3px]"
                    style={{
                      background:
                        lvl === 0
                          ? "var(--bg-inset)"
                          : `color-mix(in oklab, var(--color-danger-500) ${LEVEL_ALPHA[lvl]! * 100}%, var(--bg-inset))`,
                      outline: lvl === 0 ? "1px solid var(--border)" : "none",
                      outlineOffset: -1,
                    }}
                    initial={{ opacity: 0, scale: 0.72 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{
                      delay: Math.min(0.4, (rowIndex * days.length + colIndex) * 0.0016),
                      duration: 0.2,
                    }}
                    whileHover={{ scale: 1.42, zIndex: 2 }}
                    onMouseEnter={() => setHover(slot)}
                    onMouseLeave={() => setHover((current) => (current === slot ? null : current))}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 t-tertiary" style={{ color: "var(--text-faint)" }}>
          <span>少</span>
          {LEVEL_ALPHA.map((alpha, index) => (
            <span
              key={index}
              className="h-[9px] w-[9px] rounded-[2px]"
              style={{
                background:
                  index === 0
                    ? "var(--bg-inset)"
                    : `color-mix(in oklab, var(--color-danger-500) ${alpha * 100}%, var(--bg-inset))`,
                outline: index === 0 ? "1px solid var(--border)" : "none",
                outlineOffset: -1,
              }}
            />
          ))}
          <span>多</span>
          <span className="ml-2 inline-flex items-center gap-1">
            <span className="h-[9px] w-[9px] rounded-[2px] border border-dashed" style={{ borderColor: "var(--border)" }} />
            未运行
          </span>
        </div>
        <p className="font-mono t-eyebrow-cjk" style={{ color: "var(--text-faint)" }}>
          {hover?.cell
            ? `${hover.agent} · ${hover.day} · ${formatCount(hover.cell.runs)} 次执行 · ${formatCount(hover.cell.failures)} 次失败 · ${formatPercent(hover.cell.failures, hover.cell.runs)}`
            : `${days[0] ?? "—"} → ${days[days.length - 1] ?? "—"}`}
        </p>
      </div>
    </div>
  );
});
