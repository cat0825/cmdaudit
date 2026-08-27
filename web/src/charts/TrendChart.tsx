/**
 * 运行量 / 失败量趋势。
 *
 * 双 Y 轴是有意的：runs 与 failures 差两个量级，共轴会把失败线压成一条贴底直线。
 * 两个轴各自标注，tooltip 里同时给出失败率，避免读者用眼睛估比例。
 */
import { memo, useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TimelinePoint } from "../lib/payload";
import { formatCount, formatDayShort, formatPercent } from "../lib/format";

export interface TrendDatum extends TimelinePoint {
  label: string;
  rate: number;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: TrendDatum }[];
}) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload;
  if (!datum) return null;
  return (
    <div
      className="pointer-events-none rounded-control border px-2.5 py-2 t-label"
      style={{
        background: "var(--bg-elevated)",
        borderColor: "var(--border-strong)",
        boxShadow: "var(--shadow-pop)",
      }}
    >
      <p className="mb-1 font-mono t-label" style={{ color: "var(--text-faint)" }}>
        {datum.day}
      </p>
      <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5">
        <dt style={{ color: "var(--text-muted)" }}>执行</dt>
        <dd className="num text-right">{formatCount(datum.runs)}</dd>
        <dt style={{ color: "var(--text-danger)" }}>失败</dt>
        <dd className="num text-right" style={{ color: "var(--text-danger)" }}>
          {formatCount(datum.failures)}
        </dd>
        <dt style={{ color: "var(--text-muted)" }}>失败率</dt>
        <dd className="num text-right">{formatPercent(datum.failures, datum.runs)}</dd>
      </dl>
    </div>
  );
}

export const TrendChart = memo(function TrendChart({ points }: { points: TimelinePoint[] }) {
  const data = useMemo<TrendDatum[]>(
    () =>
      points.map((point) => ({
        ...point,
        label: formatDayShort(point.day),
        rate: point.runs ? point.failures / point.runs : 0,
      })),
    [points],
  );

  return (
    <div className="h-[188px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="var(--grid-line)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "var(--text-faint)", fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={18}
          />
          <YAxis
            yAxisId="runs"
            tick={{ fontSize: 10, fill: "var(--text-faint)", fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <YAxis
            yAxisId="failures"
            orientation="right"
            /* 轴刻度是文字，走 --text-danger（4.5），不是笔画档 --color-danger-500。 */
            tick={{ fontSize: 10, fill: "var(--text-danger)", fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            width={30}
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
          />
          <Area
            yAxisId="runs"
            type="monotone"
            dataKey="runs"
            stroke="var(--signal-live)"
            strokeWidth={1.75}
            fill="color-mix(in oklab, var(--signal-live) 14%, transparent)"
            animationDuration={520}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: "var(--signal-live)" }}
          />
          <Line
            yAxisId="failures"
            type="monotone"
            dataKey="failures"
            stroke="var(--color-danger-500)"
            strokeWidth={1.75}
            dot={false}
            animationDuration={620}
            activeDot={{ r: 3, strokeWidth: 0, fill: "var(--color-danger-500)" }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
});
