/**
 * 重试循环视图。回答一个别处看不到的问题：**哪个 agent 在哪次会话里卡在同一条命令上出不来。**
 *
 * 这是全 payload 里唯一按 `session_id` 聚合的数据 —— 别处都按模板或 agent 汇总，
 * 于是「同一次会话把同一条命令重来了 165 遍」这个事实在别处不可见。
 *
 * 口径声明（wasted_s 是下界 + 重试 ≠ 错误）必须原样出现在页面上，不能藏进 tooltip：
 * 把 tries 当错误数读会把逐段 sed 读文件误判成事故。
 */
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { ArrowDownIcon, ArrowUpIcon, CaretRightIcon, FunnelSimpleIcon } from "@phosphor-icons/react";
import type { Payload, RetryLoop } from "../lib/payload";
import { Badge, Card, CardHead, Empty, Meter } from "../components/primitives";
import { CommandBlock } from "../components/CommandBlock";
import { formatCount, formatMonthDay, formatPercent, formatSeconds } from "../lib/format";
import { LIST_CONTAINER, LIST_ITEM } from "../lib/motion";

type SortKey = "failures" | "tries" | "wasted" | "rate";
type SortDir = "asc" | "desc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "failures", label: "失败次数" },
  { key: "rate", label: "失败占比" },
  { key: "tries", label: "重跑次数" },
  { key: "wasted", label: "累计耗时" },
];

/**
 * 行网格。模板占弹性列，四个数值列定宽，避免长命令把数值列挤成折行。
 *
 * 定宽列合计 276px + gap + padding 让整行的 min-content 到 380px：在 390px 视口
 * （内容盒 358px）下装不进，会顶出 6px 横向溢出。`clip` 只是视觉截断，撑不动
 * grid 轨道下限。所以窄屏换一套更紧的列宽 —— 数值仍在同一行，只是不再留富余。
 */
const GRID_WIDE = "18px minmax(0,1fr) 58px 58px 84px 76px";
const GRID_NARROW = "14px minmax(0,1fr) 40px 36px 52px 56px";

/**
 * 窄屏判定。断点取 Tailwind 的 `sm`（640px）—— 定宽列在 640px 以下就开始吃紧，
 * 不必等到真溢出的 390px 才换。
 *
 * 用 matchMedia 而不是 CSS 类：列宽走的是 `gridTemplateColumns` 内联样式，
 * 内联样式里写不了媒体查询。
 */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 639px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const sync = () => setNarrow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return narrow;
}

/** 失败占比 → tone。低占比链多数无害（轮询/分段读取），不该染成红色。 */
function rateTone(failures: number, tries: number): "danger" | "warn" | "ok" | "neutral" {
  if (failures === 0) return "ok";
  const rate = tries ? failures / tries : 0;
  if (rate >= 0.5) return "danger";
  if (rate >= 0.2) return "warn";
  return "neutral";
}

/** 会话 id 只截断展示：全长是 uuid 级噪声，但要能靠 title 取回原值去查库。 */
function shortSession(sessionId: string): string {
  return sessionId.length > 10 ? `${sessionId.slice(0, 10)}…` : sessionId || "—";
}

function LoopRow({
  loop,
  open,
  grid,
  onToggle,
}: {
  loop: RetryLoop;
  open: boolean;
  /** 由父级按视口宽度选定，行与表头必须共用同一套列宽。 */
  grid: string;
  onToggle: () => void;
}) {
  const tone = rateTone(loop.failures, loop.tries);
  const ratio = loop.tries ? loop.failures / loop.tries : 0;

  return (
    <motion.li variants={LIST_ITEM} className="border-b last:border-b-0" style={{ borderColor: "var(--border)" }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="grid w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-[var(--bg-inset)]"
        style={{ gridTemplateColumns: grid }}
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.14 }} className="grid place-items-center">
          <CaretRightIcon size={11} style={{ color: "var(--text-faint)" }} />
        </motion.span>

        <span className="min-w-0">
          {/* 模板原文截断不换行：重试链是同一条命令的重复，对齐比看全文重要，
              全文在展开区的样本里。 */}
          <code className="clip block font-mono t-mono" title={loop.template}>
            {loop.template || "—"}
          </code>
          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 t-label" style={{ color: "var(--text-faint)" }}>
            <span style={{ color: "var(--text-muted)" }}>{loop.agent || "—"}</span>
            <span>{loop.project || "—"}</span>
            <span className="num" title={loop.session_id}>
              {shortSession(loop.session_id)}
            </span>
            <span className="num">
              {formatMonthDay(loop.first_seen)} → {formatMonthDay(loop.last_seen)}
            </span>
          </span>
        </span>

        <span className="num text-right t-body-sm" style={{ color: "var(--text-muted)" }} title="重跑次数">
          ×{formatCount(loop.tries)}
        </span>
        <span
          className="num text-right t-body-sm"
          style={{ color: loop.failures > 0 ? "var(--text-danger)" : "var(--text-faint)" }}
          title="失败次数"
        >
          {formatCount(loop.failures)}
        </span>
        <span className="min-w-0">
          <span className="num block text-right t-body-sm" style={{ color: `var(--text-${tone === "neutral" ? "muted" : tone})` }}>
            {formatPercent(loop.failures, loop.tries)}
          </span>
          <span className="mt-1 block">
            <Meter ratio={ratio} tone={tone} />
          </span>
        </span>
        <span className="num text-right t-body-sm" style={{ color: "var(--text-muted)" }} title="累计可信耗时（下界）">
          {formatSeconds(loop.wasted_s)}
        </span>
      </button>

      {open ? (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="overflow-hidden px-3 pb-3.5"
          style={{ background: "var(--bg-inset)" }}
        >
          <p className="pt-3 t-label" style={{ color: "var(--text-muted)" }}>
            按时间正序、<span style={{ color: "var(--text)" }}>故意不去重</span>
            ：同一条命令重复出现就是重试链的证据。样本每条链上限 5 条，
            不是全部 {formatCount(loop.tries)} 次。
          </p>

          <ul className="mt-2 grid gap-2">
            {loop.samples.map((sample, index) => (
              <li
                key={`${loop.loop_id}-${index}`}
                className="rounded-card border p-2.5"
                style={{ borderColor: "var(--border)", background: "var(--bg-elevated)" }}
              >
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge mono>#{index + 1}</Badge>
                  <Badge tone={sample.status === "failed" ? "danger" : "ok"} mono>
                    {sample.status} / exit {sample.exit_code ?? "—"}
                  </Badge>
                  <Badge mono>{formatSeconds(sample.duration_s)}</Badge>
                  <Badge mono>{sample.duration_source}</Badge>
                  {sample.failure_kind ? (
                    <Badge tone="warn" mono>
                      {sample.failure_kind}
                    </Badge>
                  ) : null}
                </div>
                <CommandBlock text={sample.command} wrap />
                {sample.error_snippet ? (
                  <div className="mt-2">
                    <CommandBlock text={sample.error_snippet} label="错误片段" wrap />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {loop.samples.length === 0 ? (
            <p className="mt-2 t-label" style={{ color: "var(--text-faint)" }}>
              这条链没有取到命令原文样本。
            </p>
          ) : null}

          {loop.drill_sql ? (
            <div className="mt-2.5">
              <CommandBlock text={loop.drill_sql} label="可复现 SQL" wrap />
            </div>
          ) : null}
        </motion.div>
      ) : null}
    </motion.li>
  );
}

export function LoopsView({ payload }: { payload: Payload }) {
  const loops = payload.retry_loops;
  const [agents, setAgents] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("failures");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [openId, setOpenId] = useState<string | null>(null);
  const grid = useNarrow() ? GRID_NARROW : GRID_WIDE;

  const agentFacets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const loop of loops) counts.set(loop.agent, (counts.get(loop.agent) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [loops]);

  // KPI 一律按**全部** retry_loops 算，不跟筛选走：筛选是浏览手段，
  // 让顶部数字随 chip 变会让人以为「涉及会话数」减少了。
  const kpi = useMemo(() => {
    let tries = 0;
    let wasted = 0;
    const sessions = new Set<string>();
    for (const loop of loops) {
      tries += loop.tries;
      wasted += loop.wasted_s;
      sessions.add(loop.session_id);
    }
    return { tries, wasted, sessions: sessions.size };
  }, [loops]);

  const truncated = payload.retry_loops_total > loops.length;

  const rows = useMemo(() => {
    const filtered = agents.length > 0 ? loops.filter((loop) => agents.includes(loop.agent)) : loops;
    const value = (loop: RetryLoop): number => {
      if (sortKey === "failures") return loop.failures;
      if (sortKey === "tries") return loop.tries;
      if (sortKey === "wasted") return loop.wasted_s;
      return loop.tries ? loop.failures / loop.tries : 0;
    };
    return [...filtered].sort((a, b) => {
      const cmp = value(a) - value(b);
      // 主键相等时退到失败次数再退到会话 id，保证同一份数据的顺序稳定。
      const tie = cmp !== 0 ? cmp : a.failures - b.failures || b.session_id.localeCompare(a.session_id);
      return sortDir === "desc" ? -tie : tie;
    });
  }, [loops, agents, sortKey, sortDir]);

  const metrics = [
    {
      label: "重试链条数",
      value: formatCount(payload.retry_loops_total),
      foot: truncated
        ? `共 ${formatCount(payload.retry_loops_total)} 条，仅展示前 ${formatCount(loops.length)} 条（省略 ${formatCount(payload.retry_loops_total - loops.length)} 条）`
        : "同一会话 × 同一命令模板 × 同一 agent ≥4 次",
    },
    {
      label: "涉及会话数",
      value: formatCount(kpi.sessions),
      foot: `按展示中的 ${formatCount(loops.length)} 条链去重统计`,
      accent: "var(--text-warn)",
    },
    {
      label: "累计重跑次数",
      value: formatCount(kpi.tries),
      foot: "展示中链条的 tries 之和，含成功的重跑",
    },
    {
      label: "累计可信耗时",
      value: formatSeconds(kpi.wasted),
      foot: "只累加可信耗时，是下界，不是真实等待时长",
      accent: "var(--text-danger)",
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
        {/* min-w-0：grid item 默认 min-width:auto，长中文脚注（「共 2,085 条，仅展示
            前 80 条…」）不可断行时会把轨道顶到 380px，在 390px 视口下溢出 6px。
            显式归零才让轨道跟着容器收。 */}
        {metrics.map((metric) => (
          <motion.div key={metric.label} variants={LIST_ITEM} className="surface min-w-0 p-4">
            <dt className="t-label" style={{ color: "var(--text-muted)" }}>
              {metric.label}
            </dt>
            <dd className="num mt-1.5 t-metric" style={{ color: metric.accent }}>
              {metric.value}
            </dd>
            <p className="mt-2 t-label" style={{ color: "var(--text-faint)" }}>
              {metric.foot}
            </p>
          </motion.div>
        ))}
      </motion.dl>

      <Card>
        <CardHead
          title="重试循环"
          hint="同一次会话里被反复重跑的同一条命令模板。这是唯一按会话聚合的视图 —— 别处按模板汇总，看不出「一次会话里重来 165 遍」。"
        />
        {/* 两条口径必须在正文里，不是 tooltip：读者一旦把 tries 当错误数，
            整个视图的结论就反了。 */}
        <div className="mt-3 grid gap-1.5 border-l-2 pl-2.5" style={{ borderColor: "var(--border-strong)" }}>
          <p className="max-w-[92ch] t-body-sm" style={{ color: "var(--text-muted)" }}>
            <span style={{ color: "var(--text)" }}>累计耗时是下界。</span>
            「累计可信耗时」只累加通过 DURATION_GUARD 口径的 duration_s，缺失或不可信的耗时按 0 计。
            真实等待时长只会更长，不会更短。
          </p>
          <p className="max-w-[92ch] t-body-sm" style={{ color: "var(--text-muted)" }}>
            <span style={{ color: "var(--text)" }}>重试本身不等于错误。</span>
            轮询等待、逐段 <code className="font-mono t-mono">sed -n</code> 读文件都是正常工作方式，
            高 tries、低 failures 的链通常无害。真正值得看的是
            <span style={{ color: "var(--text-danger)" }}> failures 占比高</span>的链 —— 默认排序就按失败次数。
          </p>
        </div>
      </Card>

      <Card className="!p-3">
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 t-eyebrow-cjk" style={{ color: "var(--text-faint)" }}>
            排序
          </span>
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
                  borderColor: active ? "color-mix(in oklab, var(--color-accent-400) 42%, transparent)" : "var(--border)",
                  color: active ? "var(--text-accent)" : "var(--text-muted)",
                  background: active ? "color-mix(in oklab, var(--color-accent-400) 10%, transparent)" : "var(--bg-elevated)",
                }}
              >
                {sort.label}
                {active ? (
                  sortDir === "desc" ? <ArrowDownIcon size={10} weight="bold" /> : <ArrowUpIcon size={10} weight="bold" />
                ) : null}
              </button>
            );
          })}
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <FunnelSimpleIcon size={13} style={{ color: "var(--text-faint)" }} />
          {agentFacets.map(([agent, count]) => (
            <Chip
              key={agent}
              active={agents.includes(agent)}
              onClick={() =>
                setAgents((current) =>
                  current.includes(agent) ? current.filter((item) => item !== agent) : [...current, agent],
                )
              }
              count={count}
            >
              {agent || "—"}
            </Chip>
          ))}
        </div>
      </Card>

      <Card padded={false}>
        <div
          className="grid items-center gap-3 border-b px-3 py-2 t-eyebrow-cjk"
          style={{ gridTemplateColumns: grid, borderColor: "var(--border)", color: "var(--text-faint)", background: "var(--bg-inset)" }}
        >
          <span />
          <span>命令模板 · agent / 项目 / 会话 / 时间跨度</span>
          <span className="text-right">重跑</span>
          <span className="text-right">失败</span>
          <span className="text-right">失败占比</span>
          <span className="text-right">耗时</span>
        </div>

        <motion.ul variants={LIST_CONTAINER} initial="hidden" animate="visible">
          {rows.map((loop) => (
            <LoopRow
              key={loop.loop_id}
              loop={loop}
              open={loop.loop_id === openId}
              grid={grid}
              onToggle={() => setOpenId((current) => (current === loop.loop_id ? null : loop.loop_id))}
            />
          ))}
        </motion.ul>

        {rows.length === 0 ? (
          <Empty
            title={loops.length === 0 ? "没有重试链" : "没有匹配的重试链"}
            hint={
              loops.length === 0
                ? "没有任何「同一会话 × 同一命令模板 × 同一 agent」达到 4 次重跑的门槛。4 次以下算不上链，噪声占比过高，因此不入选。"
                : "当前 agent 筛选把所有链都排除了，取消筛选即可看到全部。"
            }
          />
        ) : null}

        <footer
          className="flex flex-wrap items-center justify-between gap-3 border-t px-3 py-2 t-label"
          style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}
        >
          <span className="num">
            {formatCount(rows.length)} / {formatCount(loops.length)} 条
            {truncated ? `（总计 ${formatCount(payload.retry_loops_total)} 条）` : ""}
          </span>
          <span>点击任意一行展开命令原文样本与可复现 SQL</span>
        </footer>
      </Card>
    </div>
  );
}

/** 与 QueueView 同形的筛选 chip。两处都只有一个用法，抽公共件反而多一层间接。 */
function Chip({
  active,
  onClick,
  children,
  count,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="inline-flex items-center gap-1.5 rounded-control border px-2 py-1 t-label font-medium transition-colors"
      style={{
        borderColor: active ? "color-mix(in oklab, var(--color-accent-400) 42%, transparent)" : "var(--border)",
        background: active ? "color-mix(in oklab, var(--color-accent-400) 12%, transparent)" : "var(--bg-elevated)",
        color: active ? "var(--text-accent)" : "var(--text-muted)",
      }}
    >
      {children}
      {count !== undefined ? (
        <span className="num t-tertiary" style={{ color: "var(--text-faint)" }}>
          {formatCount(count)}
        </span>
      ) : null}
    </button>
  );
}
