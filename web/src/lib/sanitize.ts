/**
 * payload 运行时校验 + 深层补全。
 *
 * 契约（`payload.ts` ↔ `viz/model.py`）靠约定维持，但 report.html 是**单文件产物**：
 * 可以被手改、可以由旧版 Python 生成、可以在传输里被截断。浅合并
 * `{ ...EMPTY_PAYLOAD, ...parsed }` 只能补住顶层 —— payload 有 `dashboard` 但缺
 * `dashboard.heatmap_agents` 时该字段是 undefined，图表组件 `.map` 直接抛错、整页白屏。
 *
 * 所以这里逐字段校验形状：类型不对就退回该字段的空值，并记一条告警交给页面显示。
 * 出口保证与 `Payload` 类型一致，渲染层不需要再判空。
 */
import {
  EMPTY_PAYLOAD,
  type Candidate,
  type Dashboard,
  type DurationProfile,
  type Finding,
  type FindingSignal,
  type HeatCell,
  type HistogramBin,
  type Payload,
  type Row,
  type Sample,
  type Section,
  type SectionKind,
  type TimelinePoint,
  type Track,
  type TrackTone,
} from "./payload";
import { REQUIRED_COVERAGE_KEYS } from "./coverage";

/** 告警去重：一个坏字段在 120 条 finding 上重复出现时只报一次。 */
class Warnings {
  private readonly seen = new Set<string>();

  add(message: string): void {
    this.seen.add(message);
  }

  list(): string[] {
    return [...this.seen];
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function rec(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function nullableStr(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableNum(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

/**
 * 带告警的字符串数组。
 * 用在「缺了会改变页面结论」的字段上：热力图轴缺失时页面会显示「没有时间数据」，
 * 但真实原因是契约不符，不告警就是把 bug 伪装成空数据。
 * 合法的空数组不告警。
 */
function strListChecked(value: unknown, field: string, warn: Warnings): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  warn.add(`${field} 缺失或不是数组，相关图表已按空数据渲染`);
  return [];
}

/**
 * 非数组一律退回空数组：调用方拿到的一定能 `.map`。
 * 契约里所有列表字段都是必填，所以 undefined / null 同样算违约，一并告警 ——
 * 「安静地少显示一整块内容」比报错更难查。
 */
function list<T>(
  value: unknown,
  field: string,
  warn: Warnings,
  map: (item: unknown, index: number) => T,
): T[] {
  if (Array.isArray(value)) return value.map(map);
  warn.add(`${field} 缺失或不是数组，已按空列表渲染`);
  return [];
}

/**
 * 表格单元格。Python 侧目前只产标量，但 React 19 对 object child 直接 throw，
 * 所以这里把任何非标量压成字符串 —— 契约不能只靠默契维持。
 */
function cell(value: unknown): string | number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "boolean") return String(value);
  return JSON.stringify(value) ?? "—";
}

const TRACK_TONES: readonly TrackTone[] = ["failure", "duration", "exploratory"];

function trackTone(value: unknown): TrackTone {
  return TRACK_TONES.includes(value as TrackTone) ? (value as TrackTone) : "failure";
}

function sectionKind(value: unknown): SectionKind {
  return value === "bar" ? "bar" : "plain";
}

function sample(value: unknown): Sample {
  const r = rec(value);
  return {
    command: str(r.command),
    agent: str(r.agent),
    project: str(r.project),
    status: str(r.status, "unknown"),
    exit_code: nullableNum(r.exit_code),
    duration_s: nullableNum(r.duration_s),
    duration_source: str(r.duration_source, "unknown"),
    failure_kind: nullableStr(r.failure_kind),
    error_snippet: nullableStr(r.error_snippet),
  };
}

function row(value: unknown, field: string, warn: Warnings): Row {
  const r = rec(value);
  return {
    cells: Array.isArray(r.cells) ? r.cells.map(cell) : [],
    bar_ratio: num(r.bar_ratio),
    samples: list(r.samples, `${field}.samples`, warn, sample),
    drill_sql: str(r.drill_sql),
  };
}

function section(value: unknown, index: number, warn: Warnings): Section {
  const r = rec(value);
  const field = `sections[${index}]`;
  return {
    key: str(r.key) || `section-${index}`,
    title: str(r.title, "—"),
    note: str(r.note),
    kind: sectionKind(r.kind),
    columns: strList(r.columns),
    bar_column: nullableStr(r.bar_column),
    rows: list(r.rows, `${field}.rows`, warn, (item) => row(item, field, warn)),
    sql: str(r.sql),
  };
}

function track(value: unknown, index: number, warn: Warnings): Track {
  const r = rec(value);
  return {
    key: str(r.key) || `track-${index}`,
    title: str(r.title, "—"),
    tone: trackTone(r.tone),
    scope_name: str(r.scope_name, "未声明"),
    caveat: str(r.caveat),
    lead: str(r.lead),
    sections: list(r.sections, `tracks[${index}].sections`, warn, (item, at) =>
      section(item, at, warn),
    ),
  };
}

function candidate(value: unknown, index: number): Candidate {
  const r = rec(value);
  return {
    candidate_id: str(r.candidate_id) || `candidate-${index}`,
    source_rule: str(r.source_rule, "—"),
    command_shape: str(r.command_shape, "—"),
    priority: num(r.priority),
    hypothesis: str(r.hypothesis),
    design: str(r.design),
    observed: isRecord(r.observed) ? r.observed : {},
    caveats: strList(r.caveats),
  };
}

function finding(value: unknown, index: number, warn: Warnings): Finding {
  const r = rec(value);
  return {
    finding_id: str(r.finding_id) || `finding-${index}`,
    template_id: str(r.template_id, "—"),
    template: str(r.template, "—"),
    failure_kind: str(r.failure_kind, "unknown"),
    program: str(r.program),
    failures: num(r.failures),
    runs: num(r.runs),
    agents: strList(r.agents),
    projects: strList(r.projects),
    first_seen: nullableStr(r.first_seen),
    last_seen: nullableStr(r.last_seen),
    signal: list(r.signal, "findings[].signal", warn, signalPoint),
    samples: list(r.samples, "findings[].samples", warn, sample),
    drill_sql: str(r.drill_sql),
  };
}

function signalPoint(value: unknown): FindingSignal {
  const r = rec(value);
  return { day: str(r.day), failures: num(r.failures) };
}

function timelinePoint(value: unknown): TimelinePoint {
  const r = rec(value);
  return {
    day: str(r.day),
    runs: num(r.runs),
    failures: num(r.failures),
    duration_s: num(r.duration_s),
  };
}

function heatCell(value: unknown): HeatCell {
  const r = rec(value);
  return {
    agent: str(r.agent),
    day: str(r.day),
    runs: num(r.runs),
    failures: num(r.failures),
  };
}

function histogramBin(value: unknown): HistogramBin {
  const r = rec(value);
  return { lo: num(r.lo), hi: nullableNum(r.hi), count: num(r.count) };
}

/** `[string, number][]`：非二元组或类型不符的项直接丢弃。 */
function pairList(value: unknown, field: string, warn: Warnings): [string, number][] {
  if (!Array.isArray(value)) {
    warn.add(`${field} 缺失或不是数组，已按空列表渲染`);
    return [];
  }
  const pairs: [string, number][] = [];
  for (const item of value) {
    if (!Array.isArray(item) || item.length < 2) continue;
    if (typeof item[0] !== "string" || typeof item[1] !== "number") continue;
    if (!Number.isFinite(item[1])) continue;
    pairs.push([item[0], item[1]]);
  }
  if (pairs.length !== value.length) warn.add(`${field} 有条目形状不符，已跳过`);
  return pairs;
}

function durationProfile(value: unknown, warn: Warnings): DurationProfile | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    warn.add("dashboard.duration_profile 形状不符，耗时分布已隐藏");
    return null;
  }
  return {
    bins: list(value.bins, "duration_profile.bins", warn, histogramBin),
    p50: nullableNum(value.p50),
    p90: nullableNum(value.p90),
    p99: nullableNum(value.p99),
    max_s: nullableNum(value.max_s),
    sample_size: num(value.sample_size),
  };
}

function dashboard(value: unknown, warn: Warnings): Dashboard {
  if (!isRecord(value)) {
    if (value !== undefined && value !== null) warn.add("dashboard 形状不符，总览图表已按空数据渲染");
    return EMPTY_PAYLOAD.dashboard;
  }
  return {
    timeline: list(value.timeline, "dashboard.timeline", warn, timelinePoint),
    failures_by_kind: pairList(value.failures_by_kind, "dashboard.failures_by_kind", warn),
    runs_by_agent: pairList(value.runs_by_agent, "dashboard.runs_by_agent", warn),
    latest_event_at: nullableStr(value.latest_event_at),
    heatmap: list(value.heatmap, "dashboard.heatmap", warn, heatCell),
    heatmap_agents: strListChecked(value.heatmap_agents, "dashboard.heatmap_agents", warn),
    heatmap_days: strListChecked(value.heatmap_days, "dashboard.heatmap_days", warn),
    duration_profile: durationProfile(value.duration_profile, warn),
  };
}

function coverage(value: unknown, warn: Warnings): Record<string, string | number | null> {
  if (!isRecord(value)) {
    if (value !== undefined && value !== null) warn.add("coverage 形状不符，覆盖度指标按缺失处理");
    return {};
  }
  const result: Record<string, string | number | null> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (raw === null || typeof raw === "string") result[key] = raw;
    else if (typeof raw === "number") result[key] = Number.isFinite(raw) ? raw : null;
    else result[key] = null;
  }
  const missing = REQUIRED_COVERAGE_KEYS.filter((key) => !(key in result));
  if (missing.length > 0) warn.add(`coverage 缺少「${missing.join("、")}」，相关指标按 0 显示`);
  return result;
}

export interface SanitizeResult {
  payload: Payload;
  /** 契约不符导致的降级说明。与 `payload.warnings`（Python 侧生成告警）分属两类。 */
  warnings: string[];
}

/**
 * 把任意解析结果收敛成合法 `Payload`。
 * 顶层不是对象时整体退回空 payload —— 这种情况页面已经没有可展示的东西，
 * 但仍然渲染外壳并显示原因，比白屏可诊断。
 */
export function sanitizePayload(parsed: unknown): SanitizeResult {
  if (!isRecord(parsed)) {
    return {
      payload: EMPTY_PAYLOAD,
      warnings: ["payload 不是 JSON 对象，页面按空数据渲染。请重新运行 cmdaudit viz。"],
    };
  }
  const warn = new Warnings();
  const findings = list(parsed.findings, "findings", warn, (item, index) =>
    finding(item, index, warn),
  );
  // findings_total 是未截断总数，必须 ≥ 实际条数，否则总览会算出负的「省略 N 条」。
  const total = Math.max(num(parsed.findings_total), findings.length);
  return {
    payload: {
      generated_at: str(parsed.generated_at, "—"),
      source_db: str(parsed.source_db, "—"),
      coverage: coverage(parsed.coverage, warn),
      tracks: list(parsed.tracks, "tracks", warn, (item, index) => track(item, index, warn)),
      findings_total: total,
      findings,
      dashboard: dashboard(parsed.dashboard, warn),
      candidates: list(parsed.candidates, "candidates", warn, candidate),
      candidate_note: str(parsed.candidate_note),
      warnings: strList(parsed.warnings),
    },
    warnings: warn.list(),
  };
}
