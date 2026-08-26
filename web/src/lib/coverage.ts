/**
 * coverage 的键是中文字符串，由 Python 侧 `report/build.py::collect_coverage` 定义。
 *
 * 前端多处按键取值，而取不到时会被当成 0（`typeof value === "number"` 不成立）。
 * 也就是说 Python 侧改一个键名，页面上的指标会**静默归零**而不是报错。
 * 所以键名集中在这里，并由 `sanitize.ts` 在加载时校验缺失、缺了就在页面上告警。
 */

export const COVERAGE_KEY = {
  total: "命令总数",
  agents: "agent 数",
  projects: "项目数",
  failed: "判定为失败",
  succeeded: "判定为成功",
  durationSamples: "可用于耗时统计",
  durationTotalSeconds: "可信耗时合计（秒）",
} as const;

/** 页面指标依赖的键。缺任何一个都会显示加载告警，而不是安静地显示 0。 */
export const REQUIRED_COVERAGE_KEYS: readonly string[] = Object.values(COVERAGE_KEY);

/** 按键取数值。缺失或非数值退回 0 —— 展示层不负责解释为什么缺。 */
export function coverageNumber(
  coverage: Record<string, string | number | null>,
  key: string,
): number {
  const value = coverage[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
