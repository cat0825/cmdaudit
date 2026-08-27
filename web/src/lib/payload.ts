/**
 * 与 `src/cmdaudit/viz/model.py` 一一对应的只读契约。
 * 改动任何字段都必须同时改 Python 侧，否则页面会静默丢数据。
 */

export type TrackTone = "failure" | "duration" | "exploratory";
export type SectionKind = "bar" | "plain";

export interface Sample {
  command: string;
  agent: string;
  project: string;
  status: string;
  exit_code: number | null;
  duration_s: number | null;
  duration_source: string;
  failure_kind: string | null;
  error_snippet: string | null;
}

export interface Row {
  cells: (string | number | null)[];
  bar_ratio: number;
  samples: Sample[];
  drill_sql: string;
}

export interface Section {
  key: string;
  title: string;
  note: string;
  kind: SectionKind;
  columns: string[];
  bar_column: string | null;
  rows: Row[];
  sql: string;
}

export interface Track {
  key: string;
  title: string;
  tone: TrackTone;
  scope_name: string;
  caveat: string;
  lead: string;
  sections: Section[];
}

export interface Candidate {
  candidate_id: string;
  source_rule: string;
  command_shape: string;
  priority: number;
  hypothesis: string;
  design: string;
  observed: Record<string, unknown>;
  caveats: string[];
}

export interface TimelinePoint {
  day: string;
  runs: number;
  failures: number;
  duration_s: number;
}

export interface HeatCell {
  agent: string;
  day: string;
  runs: number;
  failures: number;
}

export interface HistogramBin {
  lo: number;
  hi: number | null;
  count: number;
}

export interface DurationProfile {
  bins: HistogramBin[];
  p50: number | null;
  p90: number | null;
  p99: number | null;
  max_s: number | null;
  sample_size: number;
}

export interface FindingSignal {
  day: string;
  failures: number;
}

export interface Finding {
  finding_id: string;
  template_id: string;
  template: string;
  failure_kind: string;
  program: string;
  failures: number;
  runs: number;
  agents: string[];
  projects: string[];
  first_seen: string | null;
  last_seen: string | null;
  signal: FindingSignal[];
  samples: Sample[];
  drill_sql: string;
}

export interface RetryLoop {
  loop_id: string;
  session_id: string;
  agent: string;
  project: string;
  template: string;
  template_id: string;
  tries: number;
  failures: number;
  /** 只累加可信耗时（DURATION_GUARD 口径），是下界，不含价值判断。 */
  wasted_s: number;
  first_seen: string | null;
  last_seen: string | null;
  /** 按时间正序、**不去重**：重复原文正是重试链要展示的东西。 */
  samples: Sample[];
  drill_sql: string;
}

export interface GroupProfile {
  group: string;
  runs: number;
  failures: number;
  /** 由 Python 侧算好；渲染层不做数值运算。 */
  failure_pct: number;
  duration_s: number;
  top_programs: [string, number][];
  drill_sql: string;
}

export interface Dashboard {
  timeline: TimelinePoint[];
  failures_by_kind: [string, number][];
  runs_by_agent: [string, number][];
  latest_event_at: string | null;
  heatmap: HeatCell[];
  heatmap_agents: string[];
  heatmap_days: string[];
  duration_profile: DurationProfile | null;
}

export interface Payload {
  generated_at: string;
  source_db: string;
  coverage: Record<string, string | number | null>;
  tracks: Track[];
  /** 未截断的 finding 总条数；`findings` 被 MAX_FINDINGS 截断时 KPI 必须用它。 */
  findings_total: number;
  findings: Finding[];
  /** 未截断的重试链总条数；`retry_loops` 被截断时 KPI 必须用它。 */
  retry_loops_total: number;
  retry_loops: RetryLoop[];
  group_profiles: GroupProfile[];
  dashboard: Dashboard;
  candidates: Candidate[];
  candidate_note: string;
  warnings: string[];
}

/** payload 缺失时的空壳。渲染层因此不需要到处判空。 */
export const EMPTY_PAYLOAD: Payload = {
  generated_at: "—",
  source_db: "—",
  coverage: {},
  tracks: [],
  findings_total: 0,
  findings: [],
  retry_loops_total: 0,
  retry_loops: [],
  group_profiles: [],
  dashboard: {
    timeline: [],
    failures_by_kind: [],
    runs_by_agent: [],
    latest_event_at: null,
    heatmap: [],
    heatmap_agents: [],
    heatmap_days: [],
    duration_profile: null,
  },
  candidates: [],
  candidate_note: "",
  warnings: [],
};
