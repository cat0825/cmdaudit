/** 视图定义。侧栏、⌘K、路由（hash）共用同一份，避免三处各写一遍。 */
export const VIEWS = [
  { id: "overview", label: "总览", hint: "运行信号与失败构成" },
  { id: "queue", label: "失败模式", hint: "可处理的复发失败队列" },
  { id: "board", label: "处理看板", hint: "按处理状态分列" },
  { id: "loops", label: "重试循环", hint: "同一会话内被反复重跑的命令" },
  { id: "groups", label: "命令构成", hint: "按动作类别看规模与失败率" },
  { id: "duration", label: "耗时分析", hint: "分布、分位数与最慢命令" },
  { id: "candidates", label: "验证队列", hint: "待验证候选（exploratory）" },
  { id: "evidence", label: "证据与口径", hint: "覆盖度、口径声明与原始 SQL" },
] as const;

export type ViewId = (typeof VIEWS)[number]["id"];

export function isViewId(value: string): value is ViewId {
  return VIEWS.some((view) => view.id === value);
}
