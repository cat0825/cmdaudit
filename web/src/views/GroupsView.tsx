/**
 * 命令构成：按动作类别（command_group）看规模与失败率。
 *
 * 存在意义是纠正队列视图按**绝对失败数**排序的偏差。按 template 排的队列里，
 * search_read 这类体量 14732 的类别贡献 358 次失败，永远排在前面；build 只跑了
 * 243 次却有 58 次失败（23.9%），在绝对数排序里根本看不见。这个视图专门回答
 * 「失败集中在哪类动作上」，所以它必须让「体量小失败率高」和「体量大失败率低」
 * 这一对反差成为版面上最响的东西。
 *
 * 规模与失败率走**两条独立视觉通道**，这是本视图的核心取舍：
 *   - 规模条按 max(runs) 线性归一。体量差 100 倍（133 vs 14732），container 归一后
 *     不到 1%、只剩 Meter 的 2% 下限残根 —— 这不是缺陷而是事实，条形只承载量感，
 *     精确值由紧邻的数字承载，所以「看不清长度」不会造成信息丢失。
 *   - 失败率条按 max(failure_pct) 归一，**不按 100%**。按 100% 归一时全场都挤在
 *     0–24% 的左端，2.4% 与 6.7% 的差别（近 3 倍）在版面上宽度差不到 5px，
 *     等于把这个视图唯一想说的事抹平了。按最大值归一放大了组间差异，代价是
 *     读者失去绝对参照 —— 所以同一条轨道上画出整体基线刻度，并在图例里写明，
 *     相对读法因此有锚点。
 * 反过来「一根条同时编码两者」（例如条长=runs、条色=失败率）也试过不成立：
 * 小类别的条根本没有面积去承载颜色，最需要被看见的行会变成一根看不见的细线。
 */
import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { ArrowDownIcon, ArrowUpIcon, CaretRightIcon } from "@phosphor-icons/react";
import type { GroupProfile, Payload } from "../lib/payload";
import { Badge, Card, CardHead, Empty, Meter } from "../components/primitives";
import { CommandBlock } from "../components/CommandBlock";
import { formatCount, formatPercent, formatSeconds } from "../lib/format";
import { LIST_CONTAINER, LIST_ITEM } from "../lib/motion";

type SortKey = "failure_pct" | "runs" | "failures" | "duration_s";
type SortDir = "asc" | "desc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "failure_pct", label: "失败率" },
  { key: "runs", label: "执行数" },
  { key: "failures", label: "失败数" },
  { key: "duration_s", label: "累计耗时" },
];

/**
 * 失败率轨道。比 `Meter` 多一件事：画出整体基线刻度。
 * 没有这条刻度，按最大值归一的条形就是无锚点的相对图形，读者不知道在跟什么比。
 */
function RateTrack({
  pct,
  max,
  baseline,
  above,
}: {
  pct: number;
  max: number;
  baseline: number;
  /** 是否高于整体基线。只决定笔画色，不参与宽度。 */
  above: boolean;
}) {
  const width = max > 0 ? Math.max(2, Math.min(100, (pct / max) * 100)) : 2;
  const tick = max > 0 ? Math.max(0, Math.min(100, (baseline / max) * 100)) : 0;
  return (
    <span
      className="relative block h-1 w-full overflow-hidden rounded-full"
      style={{ background: "var(--bg-inset)" }}
      aria-hidden
    >
      <span
        className="block h-full rounded-full"
        style={{ width: `${width}%`, background: above ? "var(--text-danger)" : "var(--chart-neutral)" }}
      />
      {/* 基线刻度压在条形之上：高失败率类别的条会盖过刻度位置，刻度必须仍然可见。 */}
      <span
        className="absolute top-0 h-full w-px"
        style={{ left: `${tick}%`, background: "var(--text-faint)" }}
      />
    </span>
  );
}

function GroupRow({
  profile,
  maxRuns,
  maxPct,
  baselinePct,
  open,
  onToggle,
}: {
  profile: GroupProfile;
  maxRuns: number;
  maxPct: number;
  baselinePct: number;
  open: boolean;
  onToggle: () => void;
}) {
  // 比较用的是聚合基线，不是重算 failure_pct —— 后者由 Python 给定，这里原样渲染。
  const above = profile.failure_pct > baselinePct;
  const lift = baselinePct > 0 ? profile.failure_pct / baselinePct : 0;

  return (
    <motion.li variants={LIST_ITEM} className="border-b last:border-b-0" style={{ borderColor: "var(--border)" }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="grid w-full grid-cols-[16px_minmax(0,1fr)] items-start gap-x-3 gap-y-2 px-3 py-2.5 text-left transition-colors hover:bg-[var(--bg-inset)] md:grid-cols-[16px_minmax(150px,1fr)_minmax(96px,1.15fr)_minmax(96px,1.15fr)_64px_80px] md:items-center"
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.14 }} className="grid place-items-center pt-0.5">
          <CaretRightIcon size={11} style={{ color: "var(--text-faint)" }} />
        </motion.span>

        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-1.5">
            {/* group 是小写标识符（build / search_read），走 t-eyebrow-cjk：
                t-eyebrow 会把它大写成 BUILD，那不是数据库里的值。 */}
            <code className="font-mono t-eyebrow-cjk" style={{ color: "var(--text)" }}>
              {profile.group}
            </code>
            {above ? (
              <Badge tone="danger">高于基线 {lift.toFixed(1)}×</Badge>
            ) : null}
          </span>
          {profile.top_programs.length > 0 ? (
            <span className="mt-1.5 flex flex-wrap items-center gap-1">
              {profile.top_programs.map(([program, count]) => (
                <Badge key={program} mono>
                  {program}
                  <span className="num" style={{ color: "var(--text-faint)" }}>
                    {formatCount(count)}
                  </span>
                </Badge>
              ))}
            </span>
          ) : null}
        </span>

        {/* 通道一：规模。条形只给量感，精确值靠数字。 */}
        <span className="min-w-0">
          <span className="num block text-right t-body-sm" style={{ color: "var(--text-muted)" }}>
            {formatCount(profile.runs)}
          </span>
          <span className="mt-1 block">
            <Meter ratio={maxRuns > 0 ? profile.runs / maxRuns : 0} tone="neutral" />
          </span>
        </span>

        {/* 通道二：失败率。与规模条相互独立，两条长度反向就是本视图要说的那件事。 */}
        <span className="min-w-0">
          <span
            className="num block text-right t-body-sm font-medium"
            style={{ color: above ? "var(--text-danger)" : "var(--text-muted)" }}
          >
            {profile.failure_pct.toFixed(1)}%
          </span>
          <span className="mt-1 block">
            <RateTrack pct={profile.failure_pct} max={maxPct} baseline={baselinePct} above={above} />
          </span>
        </span>

        <span className="num text-right t-body-sm" style={{ color: "var(--text-muted)" }}>
          {formatCount(profile.failures)}
        </span>
        <span className="num text-right t-body-sm" style={{ color: "var(--text-muted)" }}>
          {formatSeconds(profile.duration_s)}
        </span>
      </button>

      {open && profile.drill_sql ? (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="overflow-hidden px-3 pb-3"
          style={{ background: "var(--bg-inset)" }}
        >
          <div className="pt-2.5">
            <CommandBlock text={profile.drill_sql} label="可复现 SQL" wrap />
          </div>
        </motion.div>
      ) : null}
    </motion.li>
  );
}

export function GroupsView({ payload }: { payload: Payload }) {
  const [sortKey, setSortKey] = useState<SortKey>("failure_pct");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const profiles = payload.group_profiles;

  const totals = useMemo(() => {
    let runs = 0;
    let failures = 0;
    let maxRuns = 0;
    let maxPct = 0;
    for (const profile of profiles) {
      runs += profile.runs;
      failures += profile.failures;
      if (profile.runs > maxRuns) maxRuns = profile.runs;
      if (profile.failure_pct > maxPct) maxPct = profile.failure_pct;
    }
    // 整体失败率必须用总数算。各类别 failure_pct 的算术平均是辛普森陷阱：
    // build 的 23.9% 只压着 243 次执行，和 search_read 的 2.4%（14732 次）等权
    // 平均出来的数字不对应任何真实概率，会把整体失败率虚高好几倍。
    return { runs, failures, maxRuns, maxPct, pct: runs > 0 ? (failures / runs) * 100 : 0 };
  }, [profiles]);

  const rows = useMemo(() => {
    const value = (profile: GroupProfile): number => {
      if (sortKey === "runs") return profile.runs;
      if (sortKey === "failures") return profile.failures;
      if (sortKey === "duration_s") return profile.duration_s;
      return profile.failure_pct;
    };
    return [...profiles].sort((a, b) => {
      const cmp = value(a) - value(b) || a.group.localeCompare(b.group);
      return sortDir === "desc" ? -cmp : cmp;
    });
  }, [profiles, sortKey, sortDir]);

  const kpis = [
    { label: "动作类别", value: formatCount(profiles.length), foot: "runs ≥ 100 的类别" },
    { label: "总执行数", value: formatCount(totals.runs), foot: "已收录类别合计" },
    {
      label: "总失败数",
      value: formatCount(totals.failures),
      foot: "已收录类别合计",
      accent: "var(--text-danger)",
    },
    {
      label: "整体失败率",
      value: formatPercent(totals.failures, totals.runs),
      foot: "总失败 ÷ 总执行，非各类别失败率的平均",
      accent: "var(--text-warn)",
    },
  ];

  return (
    <div className="grid gap-3">
      <motion.dl
        variants={LIST_CONTAINER}
        initial="hidden"
        animate="visible"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        {kpis.map((kpi) => (
          <motion.div key={kpi.label} variants={LIST_ITEM} className="surface p-4">
            <dt className="t-label" style={{ color: "var(--text-muted)" }}>
              {kpi.label}
            </dt>
            <dd className="num mt-1.5 t-metric" style={{ color: kpi.accent }}>
              {kpi.value}
            </dd>
            <p className="mt-2 t-label" style={{ color: "var(--text-faint)" }}>
              {kpi.foot}
            </p>
          </motion.div>
        ))}
      </motion.dl>

      <Card padded={false}>
        <div className="px-3 pt-3">
          <CardHead
            title="按动作类别看失败集中在哪"
            hint="两条独立通道：规模条按最大执行数归一，失败率条按最高失败率归一并标出整体基线。两条长度反向的类别就是被绝对失败数排序淹没的那些。"
            action={
              <div className="flex flex-wrap items-center gap-1">
                {SORTS.map((sort) => {
                  const active = sort.key === sortKey;
                  return (
                    <button
                      key={sort.key}
                      type="button"
                      onClick={() => {
                        if (active) setSortDir(sortDir === "desc" ? "asc" : "desc");
                        else {
                          setSortKey(sort.key);
                          setSortDir("desc");
                        }
                      }}
                      aria-pressed={active}
                      className="inline-flex items-center gap-1 rounded-control border px-2 py-1 t-label transition-colors"
                      style={{
                        borderColor: active
                          ? "color-mix(in oklab, var(--color-accent-400) 42%, transparent)"
                          : "var(--border)",
                        color: active ? "var(--text-accent)" : "var(--text-muted)",
                        background: active
                          ? "color-mix(in oklab, var(--color-accent-400) 10%, transparent)"
                          : "var(--bg-elevated)",
                      }}
                    >
                      {sort.label}
                      {active ? (
                        sortDir === "desc" ? (
                          <ArrowDownIcon size={10} weight="bold" />
                        ) : (
                          <ArrowUpIcon size={10} weight="bold" />
                        )
                      ) : null}
                    </button>
                  );
                })}
              </div>
            }
          />
          {/* 口径声明必须在页面上，不能藏进 tooltip：门槛与耗时口径都会改变结论的可比性。 */}
          <p
            className="mt-2.5 mb-3 border-l-2 pl-2.5 t-label"
            style={{ borderColor: "var(--color-warn-400)", color: "var(--text-muted)" }}
          >
            只收录执行数 ≥ 100 的类别 —— 低于这个量级的失败率是噪声，一两次失败就能把百分比抬到两位数。
            累计耗时只累加可信耗时（DURATION_GUARD 口径），是下界，不是真实总耗时。
            失败率条上的竖线是整体基线 {formatPercent(totals.failures, totals.runs)}，越过它的类别按 danger 调性标注。
          </p>
        </div>

        <div
          className="hidden grid-cols-[16px_minmax(150px,1fr)_minmax(96px,1.15fr)_minmax(96px,1.15fr)_64px_80px] items-center gap-x-3 border-y px-3 py-1.5 t-eyebrow-cjk md:grid"
          style={{ borderColor: "var(--border)", color: "var(--text-faint)", background: "var(--bg-inset)" }}
        >
          <span />
          <span>动作类别 / 高频程序</span>
          <span className="text-right">执行数</span>
          <span className="text-right">失败率（基线 {formatPercent(totals.failures, totals.runs)}）</span>
          <span className="text-right">失败数</span>
          <span className="text-right">可信耗时</span>
        </div>

        <motion.ul variants={LIST_CONTAINER} initial="hidden" animate="visible">
          {rows.map((profile) => (
            <GroupRow
              key={profile.group}
              profile={profile}
              maxRuns={totals.maxRuns}
              maxPct={totals.maxPct}
              baselinePct={totals.pct}
              open={openGroup === profile.group}
              onToggle={() => setOpenGroup((current) => (current === profile.group ? null : profile.group))}
            />
          ))}
        </motion.ul>

        {rows.length === 0 ? (
          <Empty
            title="没有可用的动作类别"
            hint="没有任何 command_group 达到 100 次执行的收录门槛；样本量不足时失败率不可读，所以这里不显示低于门槛的类别。"
          />
        ) : null}
      </Card>
    </div>
  );
}
