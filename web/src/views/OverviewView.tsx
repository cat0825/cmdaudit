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
import type { ViewId } from "../lib/views";

const RANGES = [
  { id: "7", label: "7 天", days: 7 },
  { id: "14", label: "14 天", days: 14 },
  { id: "all", label: "全部", days: Number.POSITIVE_INFINITY },
] as const;

function numberOf(value: string | number | null | undefined): number {
  return typeof value === "number" ? value : 0;
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

  const points = useMemo(() => {
    const days = RANGES.find((item) => item.id === range)?.days ?? 14;
    if (!Number.isFinite(days)) return dashboard.timeline;
    return dashboard.timeline.slice(-days);
  }, [dashboard.timeline, range]);

  const windowStats = useMemo(() => {
    const runs = points.reduce((total, point) => total + point.runs, 0);
    const failures = points.reduce((total, point) => total + point.failures, 0);
    const duration = points.reduce((total, point) => total + point.duration_s, 0);
    return { runs, failures, duration };
  }, [points]);

  const total = numberOf(coverage["命令总数"]);
  const failed = numberOf(coverage["判定为失败"]);
  const maxKind = Math.max(...dashboard.failures_by_kind.map(([, count]) => count), 1);
  const topFindings = findings.slice(0, 6);
  const maxFailures = Math.max(...findings.map((item) => item.failures), 1);

  const metrics = [
    {
      label: "命令总数",
      value: formatCount(total),
      foot: `${formatCount(numberOf(coverage["agent 数"]))} 个 agent · ${formatCount(numberOf(coverage["项目数"]))} 个项目`,
    },
    {
      label: "判定为失败",
      value: formatCount(failed),
      foot: `占已判定 ${formatPercent(failed, failed + numberOf(coverage["判定为成功"]))}`,
      accent: "var(--color-danger-500)",
    },
    {
      label: "复发失败模式",
      value: formatCount(payload.findings_total),
      foot:
        payload.findings_total > findings.length
          ? `共 ${formatCount(payload.findings_total)} 条，仅展示前 ${formatCount(findings.length)} 条（省略 ${formatCount(payload.findings_total - findings.length)} 条）`
          : "同一命令模板 × 失败类型 ≥2 次",
      accent: "var(--color-warn-400)",
    },
    {
      label: "可信耗时合计",
      value: formatHours(numberOf(coverage["可信耗时合计（秒）"])),
      foot: `样本 ${formatCount(numberOf(coverage["可用于耗时统计"]))} 条（exact 口径）`,
      accent: "var(--color-accent-500)",
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
            <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {metric.label}
            </dt>
            <dd
              className="num mt-1.5 text-[24px] font-semibold leading-none"
              style={{ color: metric.accent }}
            >
              {metric.value}
            </dd>
            <p className="mt-2 text-[10.5px] leading-relaxed" style={{ color: "var(--text-faint)" }}>
              {metric.foot}
            </p>
          </motion.div>
        ))}
      </motion.dl>

      <div className="grid gap-4 xl:grid-cols-[1.55fr_1fr]">
        <Card>
          <CardHead
            title="运行信号"
            hint="左轴执行次数（面积），右轴失败次数（红线）。两轴量级不同，只看形状不看交点。"
            action={
              <div
                className="inline-flex items-center gap-px rounded-lg border p-px"
                style={{ borderColor: "var(--border)", background: "var(--bg-inset)" }}
              >
                {RANGES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setRange(item.id)}
                    aria-pressed={range === item.id}
                    className="rounded-[7px] px-2 py-[3px] text-[10.5px] font-medium transition-colors"
                    style={{
                      color: range === item.id ? "var(--color-accent-500)" : "var(--text-faint)",
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
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[10.5px]" style={{ color: "var(--text-muted)" }}>
            <div className="flex gap-1.5">
              <dt>窗口执行</dt>
              <dd className="num" style={{ color: "var(--text)" }}>{formatCount(windowStats.runs)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>窗口失败</dt>
              <dd className="num" style={{ color: "var(--color-danger-500)" }}>{formatCount(windowStats.failures)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>窗口失败率</dt>
              <dd className="num" style={{ color: "var(--text)" }}>{formatPercent(windowStats.failures, windowStats.runs)}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHead title="失败类型构成" hint="按 failure_kind 聚合全部已判定失败。" />
          <ul className="mt-3.5 grid gap-2.5">
            {dashboard.failures_by_kind.map(([kind, count]) => (
              <li key={kind} className="grid grid-cols-[76px_1fr_58px] items-center gap-2.5">
                <code className="clip font-mono text-[11px]" title={kind}>
                  {kind}
                </code>
                <Meter ratio={count / maxKind} />
                <span className="num text-right text-[11px]">
                  {formatCount(count)}
                  <span className="ml-1 text-[9.5px]" style={{ color: "var(--text-faint)" }}>
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
          hint="每格一天。虚线格代表该 agent 当天没跑命令，与「跑了但零失败」是两件事。"
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
            <h2 className="text-[13px] font-semibold tracking-tight">复发最多的失败模式</h2>
            <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
              template_id × failure_kind，按失败次数排序
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("queue")}
            className="flex items-center gap-1 text-[11.5px] transition-opacity hover:opacity-70"
            style={{ color: "var(--color-accent-500)" }}
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
                    <code className="clip font-mono text-[12px]">{finding.template}</code>
                    <Badge tone="danger" mono>
                      {finding.failure_kind}
                    </Badge>
                  </div>
                  <div className="mt-1.5 max-w-[280px]">
                    <Meter ratio={finding.failures / maxFailures} />
                  </div>
                </div>
                <span className="num text-right text-[12.5px] font-semibold" style={{ color: "var(--color-danger-500)" }}>
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
