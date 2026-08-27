/**
 * 耗时分布直方图 + 分位数标注。
 *
 * 桶宽在真实数据上是不等距的（0.1s → 120s+），所以这里**不**按 x 轴等距映射真实秒数：
 * 每个桶等宽显示，x 轴标签写明区间。用等距 x 轴画不等宽桶会让人误读密度。
 */
import { memo, useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DurationProfile } from "../lib/payload";
import { formatBinLabel, formatCount, formatPercent, formatSeconds } from "../lib/format";

interface BinDatum {
  label: string;
  count: number;
  share: string;
  hot: boolean;
}

function BinTooltip({ active, payload }: { active?: boolean; payload?: { payload: BinDatum }[] }) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload;
  if (!datum) return null;
  return (
    <div
      className="pointer-events-none rounded-control border px-2.5 py-1.5 t-label"
      style={{
        background: "var(--bg-elevated)",
        borderColor: "var(--border-strong)",
        boxShadow: "var(--shadow-pop)",
      }}
    >
      <p className="font-mono t-label" style={{ color: "var(--text-faint)" }}>
        {datum.label}
      </p>
      <p className="num mt-0.5">
        {formatCount(datum.count)} 条 · {datum.share}
      </p>
    </div>
  );
}

export const DurationHistogram = memo(function DurationHistogram({
  profile,
}: {
  profile: DurationProfile;
}) {
  const data = useMemo<BinDatum[]>(
    () =>
      profile.bins.map((bin) => ({
        label: formatBinLabel(bin.lo, bin.hi),
        count: bin.count,
        share: formatPercent(bin.count, profile.sample_size),
        // 超过 p90 的桶用实色强调：那才是值得优化的部分。
        hot: profile.p90 !== null && bin.lo >= profile.p90,
      })),
    [profile],
  );

  return (
    <div>
      <div className="h-[168px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: -20 }} barCategoryGap="16%">
            <CartesianGrid stroke="var(--grid-line)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9.5, fill: "var(--text-faint)", fontFamily: "var(--font-mono)" }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              interval={0}
              angle={-32}
              textAnchor="end"
              height={44}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--text-faint)", fontFamily: "var(--font-mono)" }}
              axisLine={false}
              tickLine={false}
              width={46}
            />
            <Tooltip content={<BinTooltip />} cursor={{ fill: "var(--bg-inset)" }} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]} animationDuration={520}>
              {data.map((datum) => (
                <Cell
                  key={datum.label}
                  fill={datum.hot ? "var(--signal-live)" : "var(--chart-neutral)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <dl className="mt-2 grid grid-cols-4 gap-px overflow-hidden rounded-card" style={{ background: "var(--border)" }}>
        {(
          [
            ["p50", profile.p50],
            ["p90", profile.p90],
            ["p99", profile.p99],
            ["max", profile.max_s],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="px-2.5 py-2" style={{ background: "var(--bg-elevated)" }}>
            <dt className="t-eyebrow" style={{ color: "var(--text-faint)" }}>
              {label}
            </dt>
            <dd className="num mt-0.5 t-body font-medium">{formatSeconds(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
});
