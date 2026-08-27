/**
 * 队列行内 sparkline。纯 SVG，不上 Recharts —— 队列有上百行，
 * 每行挂一个 ResponsiveContainer 会让滚动掉帧。
 *
 * 数据点少于 2 个时画一个点而不是一条线：一条线会暗示不存在的趋势。
 */
import { memo, useMemo } from "react";
import type { FindingSignal } from "../lib/payload";

const WIDTH = 68;
const HEIGHT = 20;

export const Sparkline = memo(function Sparkline({
  signal,
  tone = "var(--color-danger-500)",
}: {
  signal: FindingSignal[];
  tone?: string;
}) {
  const geometry = useMemo(() => {
    if (signal.length === 0) return null;
    const max = Math.max(...signal.map((point) => point.failures), 1);
    const step = signal.length > 1 ? WIDTH / (signal.length - 1) : 0;
    const points = signal.map((point, index) => {
      const x = signal.length > 1 ? index * step : WIDTH / 2;
      const y = HEIGHT - 2 - (point.failures / max) * (HEIGHT - 5);
      return { x, y };
    });
    const line = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    return { points, line, last: points[points.length - 1]! };
  }, [signal]);

  if (!geometry) {
    return <span className="inline-block" style={{ width: WIDTH, height: HEIGHT }} aria-hidden />;
  }

  if (signal.length === 1) {
    return (
      <svg width={WIDTH} height={HEIGHT} aria-hidden className="overflow-visible">
        <circle cx={geometry.last.x} cy={geometry.last.y} r={2.4} fill={tone} />
      </svg>
    );
  }

  return (
    <svg width={WIDTH} height={HEIGHT} aria-hidden className="overflow-visible">
      <path
        d={geometry.line}
        fill="none"
        stroke={tone}
        strokeWidth={1}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={geometry.last.x} cy={geometry.last.y} r={1.9} fill={tone} />
    </svg>
  );
});
