/**
 * 动效常量。集中定义，避免每个组件自己编一组时长曲线。
 * 时长上限 260ms：工作台是高频操作界面，动效必须让位于响应速度。
 */
import type { Transition, Variants } from "motion/react";

export const SPRING_POP: Transition = { type: "spring", stiffness: 420, damping: 34, mass: 0.7 };
export const SPRING_DRAWER: Transition = { type: "spring", stiffness: 360, damping: 32 };
export const EASE_OUT: Transition = { duration: 0.22, ease: [0.22, 1, 0.36, 1] };
export const EASE_FAST: Transition = { duration: 0.14, ease: [0.22, 1, 0.36, 1] };

/** 列表逐项入场。stagger 只在首次挂载跑一次，筛选时不重放。 */
export const LIST_CONTAINER: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.018, delayChildren: 0.02 } },
};

export const LIST_ITEM: Variants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: EASE_OUT },
};

export const VIEW_FADE: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: EASE_OUT },
  exit: { opacity: 0, y: -6, transition: EASE_FAST },
};
