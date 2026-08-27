/** 左侧导航。深色轨道在两种主题下都保持深色 —— 它是产品的锚点，不随内容区翻转。 */
import { clsx } from "clsx";
import { motion } from "motion/react";
import {
  ArrowsClockwiseIcon,
  ChartLineUpIcon,
  ColumnsIcon,
  DatabaseIcon,
  FlaskIcon,
  SquaresFourIcon,
  TimerIcon,
  WarningDiamondIcon,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { VIEWS, type ViewId } from "../lib/views";
import { formatCount } from "../lib/format";

const ICONS: Record<ViewId, Icon> = {
  overview: ChartLineUpIcon,
  queue: WarningDiamondIcon,
  board: ColumnsIcon,
  loops: ArrowsClockwiseIcon,
  groups: SquaresFourIcon,
  duration: TimerIcon,
  candidates: FlaskIcon,
  evidence: DatabaseIcon,
};

export function Rail({
  active,
  onSelect,
  counts,
  sourceDb,
  commandTotal,
}: {
  active: ViewId;
  onSelect: (view: ViewId) => void;
  counts: Partial<Record<ViewId, number>>;
  sourceDb: string;
  commandTotal: number;
}) {
  return (
    <nav
      aria-label="主导航"
      className="flex h-full flex-col gap-1 px-2.5 py-4"
      style={{ background: "var(--bg-rail)", color: "var(--rail-text)" }}
    >
      <div className="flex items-center gap-2 px-2 pb-4">
        <span
          className="grid h-[22px] w-[22px] place-items-center rounded-control border font-mono t-label"
          style={{
            background: "var(--rail-surface)",
            borderColor: "var(--rail-border)",
            color: "var(--rail-text)",
          }}
        >
          ca
        </span>
        <span className="t-title">cmdaudit</span>
      </div>

      <div
        className="mx-1 mb-3 rounded-card border px-2.5 py-2"
        style={{ borderColor: "var(--rail-border)", background: "var(--rail-surface)" }}
      >
        <p className="t-eyebrow-cjk" style={{ color: "var(--rail-faint)" }}>
          数据源
        </p>
        <p className="clip mt-0.5 font-mono t-label" title={sourceDb} style={{ color: "var(--rail-text)" }}>
          {sourceDb.split("/").pop()}
        </p>
        <p className="num mt-1 t-label" style={{ color: "var(--rail-muted)" }}>
          {formatCount(commandTotal)} 条命令
        </p>
      </div>

      <ul className="flex flex-col gap-0.5">
        {VIEWS.map((view) => {
          const IconComponent = ICONS[view.id];
          const selected = view.id === active;
          const count = counts[view.id];
          return (
            <li key={view.id}>
              <button
                type="button"
                onClick={() => onSelect(view.id)}
                aria-current={selected ? "page" : undefined}
                title={view.hint}
                className={clsx(
                  "relative flex w-full items-center gap-2.5 rounded-control px-2.5 py-[7px] text-left t-body transition-colors duration-150",
                  selected ? "font-medium" : "hover:bg-white/[0.055]",
                )}
                style={{ color: selected ? "var(--rail-text)" : "var(--rail-muted)" }}
              >
                {selected ? (
                  <motion.span
                    layoutId="rail-active"
                    className="absolute inset-0 rounded-control"
                    style={{ background: "var(--rail-selected)" }}
                    transition={{ type: "spring", stiffness: 480, damping: 38 }}
                  />
                ) : null}
                <IconComponent
                  size={15}
                  weight={selected ? "fill" : "regular"}
                  className="relative shrink-0"
                  style={{ color: selected ? "var(--color-accent-400)" : "var(--rail-faint)" }}
                />
                <span className="relative flex-1 truncate">{view.label}</span>
                {count !== undefined && count > 0 ? (
                  <span className="num relative t-label" style={{ color: "var(--rail-muted)" }}>
                    {formatCount(count)}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      <p
        className="mt-auto px-2.5 pt-4 t-tertiary"
        style={{ color: "var(--rail-faint)" }}
      >
        证据只读，处理状态存在本机浏览器。
        <br />
        跨轨道数字口径不同，不可相加。
      </p>
    </nav>
  );
}
