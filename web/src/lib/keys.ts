/**
 * 键盘作用域仲裁。
 *
 * App、QueueView、CommandPalette 都要响应按键。各自挂 window 监听时，缝隙会在
 * 层间漏出：面板打开、焦点在遮罩后面，队列的 j/k 仍在后台移动选中行，Enter 还能
 * 再开一个抽屉。修法不是在每个组件里各加一个守卫，而是把「现在哪一层拿键盘」
 * 收敛成一个显式值，由 App 单点计算后下发。
 *
 * - `palette`：命令面板独占，其它层全部让位。
 * - `drawer`：抽屉打开，只放行 j/k（并让抽屉内容跟着走），不放行 Enter/x。
 * - `list`：常态，列表快捷键全开。
 */
export type KeyScope = "palette" | "drawer" | "list";

/** 焦点在可输入元素里时让位给输入，否则打字会触发列表快捷键。 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
}
