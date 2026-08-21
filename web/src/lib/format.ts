/** 展示格式化。所有数字进 UI 前都过这里，避免各组件各写一套精度。 */

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** 秒 → 人类可读。跨量级切换单位，但保持两位有效数字的量感。 */
export function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value < 0.001) return "0ms";
  if (value < 1) return `${Math.round(value * 1000)}ms`;
  if (value < 60) return `${value < 10 ? value.toFixed(2) : value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  if (minutes < 60) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function formatHours(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  return `${(seconds / 3600).toFixed(1)}h`;
}

export function formatPercent(part: number, total: number): string {
  if (!total) return "—";
  const pct = (part / total) * 100;
  if (pct > 0 && pct < 0.1) return "<0.1%";
  return `${pct < 10 ? pct.toFixed(1) : Math.round(pct)}%`;
}

/** ISO 时间戳 → 短日期。解析失败时原样返回，绝不编造时间。 */
export function formatDay(value: string | null | undefined): string {
  if (!value) return "—";
  const stamp = Date.parse(value);
  if (Number.isNaN(stamp)) return value.slice(0, 10) || "—";
  return new Date(stamp).toISOString().slice(0, 10);
}

export function formatDayShort(day: string): string {
  const parts = day.split("-");
  if (parts.length < 3) return day;
  return `${parts[1]}/${parts[2]}`;
}

/** 相对「数据里的最新时间」的天数差；没有基准时退回绝对日期。 */
export function formatRelative(value: string | null, reference: string | null): string {
  if (!value) return "—";
  const target = Date.parse(value);
  const base = reference ? Date.parse(reference) : Number.NaN;
  if (Number.isNaN(target) || Number.isNaN(base)) return formatDay(value);
  const days = Math.round((base - target) / 86_400_000);
  if (days <= 0) return "最新";
  if (days === 1) return "1 天前";
  if (days < 30) return `${days} 天前`;
  return formatDay(value);
}

export function formatBinLabel(lo: number, hi: number | null): string {
  const left = lo < 1 ? `${lo * 1000}ms` : `${lo}s`;
  if (hi === null) return `≥${left}`;
  const right = hi < 1 ? `${hi * 1000}ms` : `${hi}s`;
  return `${left}–${right}`;
}
