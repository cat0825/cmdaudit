/**
 * 失败模式队列。多维筛选 + 列排序 + 键盘导航 + 批量状态操作。
 * 筛选一律在客户端做：payload 已全量在内存里，没有必要也没有后端可以查。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { ArrowDownIcon, ArrowUpIcon, FunnelSimpleIcon, XIcon } from "@phosphor-icons/react";
import type { Finding, Payload } from "../lib/payload";
import { Card, Empty, Kbd } from "../components/primitives";
import { FindingRow } from "../components/FindingRow";
import { StatusSwitch } from "../components/StatusPill";
import { STATUS_LABEL, TRIAGE_STATUSES, entryFor, type TriageEntry, type TriageMap, type TriageStatus } from "../lib/triage";
import { formatCount } from "../lib/format";
import { LIST_CONTAINER } from "../lib/motion";

type SortKey = "failures" | "rate" | "last_seen" | "runs";
type SortDir = "asc" | "desc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "failures", label: "失败次数" },
  { key: "rate", label: "失败率" },
  { key: "runs", label: "执行次数" },
  { key: "last_seen", label: "最近发生" },
];

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
      className="inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors"
      style={{
        borderColor: active ? "color-mix(in oklab, var(--color-accent-400) 42%, transparent)" : "var(--border)",
        background: active ? "color-mix(in oklab, var(--color-accent-400) 12%, transparent)" : "var(--bg-elevated)",
        color: active ? "var(--color-accent-500)" : "var(--text-muted)",
      }}
    >
      {children}
      {count !== undefined ? (
        <span className="num text-[9.5px]" style={{ color: "var(--text-faint)" }}>
          {formatCount(count)}
        </span>
      ) : null}
    </button>
  );
}

export function QueueView({
  payload,
  triage,
  selectedId,
  onSelect,
  onOpen,
  onPatchMany,
}: {
  payload: Payload;
  triage: TriageMap;
  selectedId: string | null;
  onSelect: (findingId: string | null) => void;
  onOpen: (findingId: string) => void;
  onPatchMany: (ids: string[], patch: Partial<TriageEntry>) => void;
}) {
  const [query, setQuery] = useState("");
  const [kinds, setKinds] = useState<string[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<TriageStatus[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("failures");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const listRef = useRef<HTMLDivElement>(null);

  const facets = useMemo(() => {
    const kindCount = new Map<string, number>();
    const agentCount = new Map<string, number>();
    for (const finding of payload.findings) {
      kindCount.set(finding.failure_kind, (kindCount.get(finding.failure_kind) ?? 0) + 1);
      for (const agent of finding.agents) {
        agentCount.set(agent, (agentCount.get(agent) ?? 0) + 1);
      }
    }
    const sortDesc = (entries: Map<string, number>) =>
      [...entries.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return { kinds: sortDesc(kindCount), agents: sortDesc(agentCount) };
  }, [payload.findings]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = payload.findings.filter((finding) => {
      if (kinds.length > 0 && !kinds.includes(finding.failure_kind)) return false;
      if (agents.length > 0 && !finding.agents.some((agent) => agents.includes(agent))) return false;
      if (statuses.length > 0 && !statuses.includes(entryFor(triage, finding.finding_id).status)) return false;
      if (!needle) return true;
      return (
        finding.template.toLowerCase().includes(needle) ||
        finding.program.toLowerCase().includes(needle) ||
        finding.failure_kind.toLowerCase().includes(needle) ||
        finding.projects.some((project) => project.toLowerCase().includes(needle)) ||
        finding.agents.some((agent) => agent.toLowerCase().includes(needle))
      );
    });
    const rate = (finding: Finding) => (finding.runs ? finding.failures / finding.runs : 0);
    const value = (finding: Finding): number | string => {
      if (sortKey === "failures") return finding.failures;
      if (sortKey === "runs") return finding.runs;
      if (sortKey === "rate") return rate(finding);
      return finding.last_seen ?? "";
    };
    return [...filtered].sort((a, b) => {
      const left = value(a);
      const right = value(b);
      const cmp = typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right));
      return sortDir === "desc" ? -cmp : cmp;
    });
  }, [payload.findings, query, kinds, agents, statuses, triage, sortKey, sortDir]);

  const maxFailures = useMemo(
    () => Math.max(...payload.findings.map((finding) => finding.failures), 1),
    [payload.findings],
  );

  const activeFilterCount = kinds.length + agents.length + statuses.length + (query.trim() ? 1 : 0);

  const clearFilters = useCallback(() => {
    setQuery("");
    setKinds([]);
    setAgents([]);
    setStatuses([]);
  }, []);

  const toggle = <T,>(list: T[], setList: (next: T[]) => void, value: T) => {
    setList(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  };

  // j/k 在队列内移动选中行，x 切换勾选，Enter 打开详情。
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const index = rows.findIndex((finding) => finding.finding_id === selectedId);
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        const next = rows[Math.min(rows.length - 1, index + 1)] ?? rows[0];
        if (next) onSelect(next.finding_id);
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = index <= 0 ? rows[0] : rows[index - 1];
        if (next) onSelect(next.finding_id);
      } else if (event.key === "Enter" && selectedId) {
        event.preventDefault();
        onOpen(selectedId);
      } else if (event.key === "x" && selectedId) {
        event.preventDefault();
        setChecked((current) => {
          const next = new Set(current);
          if (next.has(selectedId)) next.delete(selectedId);
          else next.add(selectedId);
          return next;
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [rows, selectedId, onSelect, onOpen]);

  useEffect(() => {
    if (!selectedId) return;
    listRef.current
      ?.querySelector<HTMLElement>('[data-selected="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const checkedIds = [...checked].filter((id) => rows.some((finding) => finding.finding_id === id));

  return (
    <div className="grid gap-3">
      <Card className="!p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索命令模板 / 程序 / 项目 / agent / 失败类型"
              className="w-full rounded-lg border px-2.5 py-1.5 text-[12px] outline-none transition-colors focus:border-[var(--color-accent-400)]"
              style={{ background: "var(--bg-inset)", borderColor: "var(--border)", color: "var(--text)" }}
            />
          </div>
          <div className="flex items-center gap-1">
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
                  className="inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] transition-colors"
                  style={{
                    borderColor: active ? "color-mix(in oklab, var(--color-accent-400) 42%, transparent)" : "var(--border)",
                    color: active ? "var(--color-accent-500)" : "var(--text-muted)",
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
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <FunnelSimpleIcon size={13} style={{ color: "var(--text-faint)" }} />
          {facets.kinds.map(([kind, count]) => (
            <Chip key={kind} active={kinds.includes(kind)} onClick={() => toggle(kinds, setKinds, kind)} count={count}>
              {kind}
            </Chip>
          ))}
          <span className="mx-1 h-4 w-px" style={{ background: "var(--border)" }} />
          {facets.agents.map(([agent, count]) => (
            <Chip key={agent} active={agents.includes(agent)} onClick={() => toggle(agents, setAgents, agent)} count={count}>
              {agent}
            </Chip>
          ))}
          <span className="mx-1 h-4 w-px" style={{ background: "var(--border)" }} />
          {TRIAGE_STATUSES.map((status) => (
            <Chip key={status} active={statuses.includes(status)} onClick={() => toggle(statuses, setStatuses, status)}>
              {STATUS_LABEL[status]}
            </Chip>
          ))}
          {activeFilterCount > 0 ? (
            <button
              type="button"
              onClick={clearFilters}
              className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] transition-colors hover:bg-[var(--bg-inset)]"
              style={{ color: "var(--text-muted)" }}
            >
              <XIcon size={11} />
              清除筛选（{activeFilterCount}）
            </button>
          ) : null}
        </div>
      </Card>

      {checkedIds.length > 0 ? (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="surface flex flex-wrap items-center gap-3 !p-2.5"
        >
          <span className="num text-[11.5px] font-medium">已选 {checkedIds.length} 条</span>
          <StatusSwitch
            value={entryFor(triage, checkedIds[0]!).status}
            size="sm"
            onChange={(status) => {
              onPatchMany(checkedIds, { status });
              setChecked(new Set());
            }}
          />
          <button
            type="button"
            onClick={() => setChecked(new Set())}
            className="ml-auto text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            取消选择
          </button>
        </motion.div>
      ) : null}

      <Card padded={false}>
        <div
          className="grid grid-cols-[22px_18px_minmax(0,1fr)_auto] items-center gap-x-3 border-b px-3 py-2 text-[9.5px] uppercase tracking-wide md:grid-cols-[22px_18px_minmax(0,1fr)_96px_78px_128px]"
          style={{ borderColor: "var(--border)", color: "var(--text-faint)", background: "var(--bg-inset)" }}
        >
          <span />
          <span />
          <span>命令模板</span>
          <span className="hidden text-right md:block">失败</span>
          <span className="hidden text-right md:block">失败率</span>
          <span className="hidden justify-self-end md:block">近 21 天</span>
          <span className="text-right md:hidden">失败</span>
        </div>

        <div ref={listRef} className="max-h-[calc(100vh-320px)] overflow-y-auto">
          <motion.ul variants={LIST_CONTAINER} initial="hidden" animate="visible">
            {rows.map((finding) => (
              <FindingRow
                key={finding.finding_id}
                finding={finding}
                entry={entryFor(triage, finding.finding_id)}
                maxFailures={maxFailures}
                selected={finding.finding_id === selectedId}
                checked={checked.has(finding.finding_id)}
                latestEventAt={payload.dashboard.latest_event_at}
                onOpen={() => {
                  onSelect(finding.finding_id);
                  onOpen(finding.finding_id);
                }}
                onToggleCheck={() =>
                  setChecked((current) => {
                    const next = new Set(current);
                    if (next.has(finding.finding_id)) next.delete(finding.finding_id);
                    else next.add(finding.finding_id);
                    return next;
                  })
                }
              />
            ))}
          </motion.ul>
          {rows.length === 0 ? (
            <Empty
              title="没有匹配的失败模式"
              hint={
                payload.findings.length === 0
                  ? "commands 表里没有复发 ≥2 次的 template_id × failure_kind 组合。"
                  : "当前筛选条件过窄，试试清除筛选。"
              }
            />
          ) : null}
        </div>

        <footer
          className="flex flex-wrap items-center justify-between gap-3 border-t px-3 py-2 text-[10.5px]"
          style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}
        >
          <span className="num">
            {formatCount(rows.length)} / {formatCount(payload.findings.length)} 条
          </span>
          <span className="flex items-center gap-2">
            <span className="flex items-center gap-1">
              <Kbd>J</Kbd>
              <Kbd>K</Kbd> 移动
            </span>
            <span className="flex items-center gap-1">
              <Kbd>X</Kbd> 勾选
            </span>
            <span className="flex items-center gap-1">
              <Kbd>↵</Kbd> 详情
            </span>
          </span>
        </footer>
      </Card>
    </div>
  );
}
