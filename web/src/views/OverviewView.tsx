/**
 * 总览。四张指标 + 趋势 + 失败构成 + 热力图 + 队列前几条。
 * 指标卡刻意不放「平均耗时」：混口径的均值是这个项目明确禁止的数字。
 */
import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { ArrowRightIcon } from "@phosphor-icons/react";
import type { Payload } from "../lib/payload";
import { Badge, Card, CardHead, Empty, Meter } from "../components/primitives";
import { TrendChart } from "../charts/TrendChart";
import { Heatmap } from "../charts/Heatmap";
import { formatCount, formatHours, formatPercent } from "../lib/format";
import { LIST_CONTAINER, LIST_ITEM } from "../lib/motion";
import { COVERAGE_KEY, coverageNumber } from "../lib/coverage";
import type { ViewId } from "../lib/views";

/**
 * issue #17：这里的「7 天」此前是「最近 7 个有数据的日期」—— 后端按 day 分组后
 * LIMIT 21，前端再 slice(-7)。稀疏使用时那 7 个活跃日可能跨越数周甚至数月，
 * 而按钮上写的是「7 天」。
 *
 * 改成真实日历窗：以数据里的最后一天为锚点，按日期过滤而不是按数组位置切片。
 * 窗口内没有活动的日期就是没有数据点，不填零 —— 那会把「没跑」画成「跑了 0 次」。
 */
const RANGES = [
  { id: "7", label: "7 天", days: 7 },
  { id: "14", label: "14 天", days: 14 },
  { id: "all", label: "全部", days: null },
] as const;

/** `YYYY-MM-DD` 往前推 n 天。用 UTC 避免本地时区把日期挪一天。 */
function shiftDay(day: string, n: number): string {
  const at = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return day;
  at.setUTCDate(at.getUTCDate() - n);
  return at.toISOString().slice(0, 10);
}

export function OverviewView({
  payload,
  onNavigate,
  onOpenFinding,
}: {
  payload: Payload;
  onNavigate: (view: ViewId) => void;
  onOpenFinding: (findingId: string) => void;
}) {
  const [range, setRange] = useState<(typeof RANGES)[number]["id"]>("14");
  const { dashboard, coverage, findings } = payload;

  const timeline = dashboard.timeline;
  //锚点是数据里的最后一天，不是今天：审计时最后一次跑 agent 可能是几天前，
  // 用今天当锚点会让「7 天」窗口大概率空着。
  const anchor = timeline.at(-1)?.day ?? null;

  const { points, windowLabel } = useMemo(() => {
    const days = RANGES.find((item) => item.id === range)?.days ?? null;
    if (days === null || anchor === null) {
      // 「全部」受后端 LIMIT 约束，是活跃日不是日历日，标签必须说清。
      const span = timeline.length;
      return {
        points: timeline,
        windowLabel: span > 0 ? `最近 ${span} 个有数据的日期` : "没有时间数据",
      };
    }
    const from = shiftDay(anchor, days - 1);
    return {
      points: timeline.filter((point) => point.day >= from),
      windowLabel: `${from} 至 ${anchor}（${days} 个日历日）`,
    };
  }, [timeline, range, anchor]);

  const windowStats = useMemo(() => {
    const runs = points.reduce((total, point) => total + point.runs, 0);
    const failures = points.reduce((total, point) => total + point.failures, 0);
    // 窗口内有数据的日期数。与日历日数不同，稀疏使用时差得很远。
    const activeDays = points.length;
    return { runs, failures, activeDays };
  }, [points]);

  // coverage 的键由 Python 侧定义，集中在 lib/coverage.ts；缺键会在加载时告警，
  // 不再是这里静默取到 0。
  const total = coverageNumber(coverage, COVERAGE_KEY.total);
  const failed = coverageNumber(coverage, COVERAGE_KEY.failed);
  const maxKind = Math.max(...dashboard.failures_by_kind.map(([, count]) => count), 1);
  const topFindings = findings.slice(0, 6);
  const maxFailures = Math.max(...findings.map((item) => item.failures), 1);

  // 四张卡全部是全历史口径，不受时间按钮影响（issue #17：此前没说，读者会以为
  // 同屏所有数字共用一个窗口）。
  const metrics = [
    {
      label: "命令总数",
      value: formatCount(total),
      foot: `全历史 · ${formatCount(coverageNumber(coverage, COVERAGE_KEY.agents))} 个 agent · ${formatCount(coverageNumber(coverage, COVERAGE_KEY.projects))} 个项目`,
    },
    {
      label: "判定为失败",
      value: formatCount(failed),
      foot: `全历史 · 占已判定 ${formatPercent(failed, failed + coverageNumber(coverage, COVERAGE_KEY.succeeded))}`,
      accent: "var(--text-danger)",
    },
    {
      label: "复发失败模式",
      value: formatCount(payload.findings_total),
      foot:
        payload.findings_total > findings.length
          ? `共 ${formatCount(payload.findings_total)} 条，仅展示前 ${formatCount(findings.length)} 条（省略 ${formatCount(payload.findings_total - findings.length)} 条）`
          : "同一命令模板 × 失败类型 ≥2 次",
      accent: "var(--text-warn)",
    },
    {
      label: "可信耗时合计",
      value: formatHours(coverageNumber(coverage, COVERAGE_KEY.durationTotalSeconds)),
      foot: `样本 ${formatCount(coverageNumber(coverage, COVERAGE_KEY.durationSamples))} 条（exact 口径）`,
      accent: "var(--signal-live)",
    },
  ];

  return (
    <div className="grid gap-4">
      <motion.dl
        variants={LIST_CONTAINER}
        initial="hidden"
        animate="visible"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        {metrics.map((metric) => (
          <motion.div key={metric.label} variants={LIST_ITEM} className="surface p-4">
            <dt className="t-label" style={{ color: "var(--text-muted)" }}>
              {metric.label}
            </dt>
            <dd
              className="num mt-1.5 t-metric"
              style={{ color: metric.accent }}
            >
              {metric.value}
            </dd>
            <p className="mt-2 t-label" style={{ color: "var(--text-faint)" }}>
              {metric.foot}
            </p>
          </motion.div>
        ))}
      </motion.dl>

      <div className="grid gap-4 xl:grid-cols-[1.55fr_1fr]">
        <Card>
          <CardHead
            title="运行信号"
            hint={
              "左轴执行次数（面积），右轴失败次数（红线）。两轴量级不同，只看形状不看交点。" +
              `范围只作用于本图与下方三项窗口统计，同屏其他区块不随它变。当前：${windowLabel}。`
            }
            action={
              <div
                className="inline-flex items-center gap-px rounded-control border p-px"
                style={{ borderColor: "var(--border)", background: "var(--bg-inset)" }}
              >
                {RANGES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setRange(item.id)}
                    aria-pressed={range === item.id}
                    className="rounded-control px-2 py-[3px] t-label font-medium transition-colors"
                    style={{
                      color: range === item.id ? "var(--text-accent)" : "var(--text-faint)",
                      background: range === item.id ? "var(--bg-elevated)" : "transparent",
                      boxShadow: range === item.id ? "var(--shadow-card)" : "none",
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="mt-3">
            {points.length > 0 ? <TrendChart points={points} /> : <Empty title="时间线为空" hint="commands 表里没有可解析的 started_at。" />}
          </div>
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 t-label" style={{ color: "var(--text-muted)" }}>
            <div className="flex gap-1.5">
              <dt>窗口执行</dt>
              <dd className="num" style={{ color: "var(--text)" }}>{formatCount(windowStats.runs)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>窗口失败</dt>
              <dd className="num" style={{ color: "var(--text-danger)" }}>{formatCount(windowStats.failures)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>窗口失败率</dt>
              <dd className="num" style={{ color: "var(--text)" }}>{formatPercent(windowStats.failures, windowStats.runs)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>其中有数据的日期</dt>
              {/* 日历日与活跃日的差就是稀疏程度。issue #17 前者被当成后者用。 */}
              <dd className="num" style={{ color: "var(--text)" }}>{formatCount(windowStats.activeDays)}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHead
            title="失败类型构成"
            hint="按 failure_kind 聚合全部已判定失败。范围是全历史，不受左侧时间按钮影响。"
          />
          <ul className="mt-3.5 grid gap-2.5">
            {dashboard.failures_by_kind.map(([kind, count]) => (
              <li key={kind} className="grid grid-cols-[76px_1fr_58px] items-center gap-2.5">
                <code className="clip font-mono t-label" title={kind}>
                  {kind}
                </code>
                <Meter ratio={count / maxKind} />
                <span className="num text-right t-label">
                  {formatCount(count)}
                  <span className="ml-1 t-tertiary" style={{ color: "var(--text-faint)" }}>
                    {formatPercent(count, failed)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          {dashboard.failures_by_kind.length === 0 ? <Empty title="没有失败记录" /> : null}
        </Card>
      </div>

      <Card>
        <CardHead
          title="agent × 日期 失败密度"
          hint={
            "每格一天。虚线格代表该 agent 当天没跑命令，与「跑了但零失败」是两件事。" +
            // issue #17：这里是活跃日不是日历日，且与上方时间按钮无关，必须说清。
            `范围是最近 ${dashboard.heatmap_days.length} 个有数据的日期，不受上方时间按钮影响。`
          }
        />
        <div className="mt-3.5">
          {dashboard.heatmap_agents.length > 0 ? (
            <Heatmap agents={dashboard.heatmap_agents} days={dashboard.heatmap_days} cells={dashboard.heatmap} />
          ) : (
            <Empty title="没有可用于热力图的时间数据" />
          )}
        </div>
      </Card>

      <Card padded={false}>
        <div className="flex items-center justify-between gap-3 border-b px-5 py-4" style={{ borderColor: "var(--border)" }}>
          <div>
            <h2 className="t-title font-medium">复发最多的失败模式</h2>
            <p className="mt-1 t-label" style={{ color: "var(--text-muted)" }}>
              template_id × failure_kind，按失败次数排序
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("queue")}
            className="flex items-center gap-1 t-body-sm transition-opacity hover:opacity-70"
            style={{ color: "var(--text-accent)" }}
          >
            打开队列
            <ArrowRightIcon size={12} />
          </button>
        </div>
        <ul>
          {topFindings.map((finding) => (
            <li key={finding.finding_id}>
              <button
                type="button"
                onClick={() => onOpenFinding(finding.finding_id)}
                className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b px-5 py-2.5 text-left transition-colors hover:bg-[var(--bg-inset)]"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <code className="clip font-mono t-mono">{finding.template}</code>
                    <Badge tone="danger" mono>
                      {finding.failure_kind}
                    </Badge>
                  </div>
                  <div className="mt-1.5 max-w-[280px]">
                    <Meter ratio={finding.failures / maxFailures} />
                  </div>
                </div>
                <span className="num text-right t-body font-medium" style={{ color: "var(--text-danger)" }}>
                  {formatCount(finding.failures)}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {topFindings.length === 0 ? <Empty title="没有复发失败模式" hint="所有失败都只出现过一次。" /> : null}
      </Card>
    </div>
  );
}
