/** 左侧导航。深色轨道在两种主题下都保持深色 —— 它是产品的锚点，不随内容区翻转。 */
import { clsx } from "clsx";
import { motion } from "motion/react";
import {
  ChartLineUpIcon,
  ColumnsIcon,
  DatabaseIcon,
  FlaskIcon,
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
      style={{ background: "oklch(0.145 0.006 265)", color: "oklch(0.92 0.004 265)" }}
    >
      <div className="flex items-center gap-2 px-2 pb-4">
        <span
          className="grid h-[22px] w-[22px] place-items-center rounded-[7px] font-mono text-[11px] font-bold"
          style={{ background: "var(--color-accent-500)", color: "white" }}
        >
          ca
        </span>
        <span className="text-[13.5px] font-semibold tracking-tight">cmdaudit</span>
      </div>

      <div
        className="mx-1 mb-3 rounded-lg border px-2.5 py-2"
        style={{ borderColor: "oklch(0.32 0.01 265)", background: "oklch(0.19 0.007 265)" }}
      >
        <p className="text-[9.5px] uppercase tracking-[0.08em]" style={{ color: "oklch(0.60 0.01 265)" }}>
          数据源
        </p>
        <p className="clip mt-0.5 font-mono text-[11px]" title={sourceDb} style={{ color: "oklch(0.97 0 0)" }}>
          {sourceDb.split("/").pop()}
        </p>
        <p className="num mt-1 text-[10.5px]" style={{ color: "oklch(0.62 0.01 265)" }}>
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
                  "relative flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-left text-[12.5px] transition-colors duration-150",
                  selected ? "font-medium" : "hover:bg-white/[0.055]",
                )}
                style={{ color: selected ? "oklch(0.99 0 0)" : "oklch(0.72 0.01 265)" }}
              >
                {selected ? (
                  <motion.span
                    layoutId="rail-active"
                    className="absolute inset-0 rounded-lg"
                    style={{ background: "oklch(0.265 0.012 265)" }}
                    transition={{ type: "spring", stiffness: 480, damping: 38 }}
                  />
                ) : null}
                <IconComponent
                  size={15}
                  weight={selected ? "fill" : "regular"}
                  className="relative shrink-0"
                  style={{ color: selected ? "var(--color-accent-400)" : "oklch(0.60 0.01 265)" }}
                />
                <span className="relative flex-1 truncate">{view.label}</span>
                {count !== undefined && count > 0 ? (
                  <span className="num relative text-[10.5px]" style={{ color: "oklch(0.62 0.01 265)" }}>
                    {formatCount(count)}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      <p
        className="mt-auto px-2.5 pt-4 text-[10px] leading-relaxed"
        style={{ color: "oklch(0.54 0.01 265)" }}
      >
        证据只读，处理状态存在本机浏览器。
        <br />
        跨轨道数字口径不同，不可相加。
      </p>
    </nav>
  );
}
