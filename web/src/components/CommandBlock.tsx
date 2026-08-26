/**
 * 命令原文 / SQL 展示块。
 * 命令原文是外部数据，这里只作为文本节点渲染（React 默认转义），不用 dangerouslySetInnerHTML。
 */
import { useCallback, useRef, useState } from "react";
import { CheckIcon, CopyIcon, WarningIcon } from "@phosphor-icons/react";

type CopyState = "idle" | "copied" | "failed";

/**
 * execCommand 回退。返回是否真的复制成功。
 *
 * 本产品主分发形态是 file:// 单文件 HTML。实测 Chromium 把 file:// 当作可信来源
 * （`isSecureContext === true`），所以 `navigator.clipboard` 存在 —— 但 writeText
 * 仍会以 `NotAllowedError` 拒绝：文档未聚焦、权限策略、无用户激活都会触发。
 * 所以这条回退不是冗余分支，而是常见路径；失败还必须看得见。
 */
function legacyCopy(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "0";
  area.style.opacity = "0";
  document.body.append(area);
  try {
    area.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

export function CommandBlock({
  text,
  label,
  wrap = false,
}: {
  text: string;
  label?: string;
  wrap?: boolean;
}) {
  const [state, setState] = useState<CopyState>("idle");
  const preRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | undefined>(undefined);

  const flash = useCallback((next: Exclude<CopyState, "idle">) => {
    setState(next);
    window.clearTimeout(timerRef.current);
    // 失败态留久一点：用户需要时间看清提示并改用手动选中。
    timerRef.current = window.setTimeout(() => setState("idle"), next === "copied" ? 1400 : 2600);
  }, []);

  const copy = useCallback(async () => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        flash("copied");
        return;
      } catch {
        /* 非安全上下文：落到 execCommand 回退，不静默吞掉 */
      }
    }
    if (legacyCopy(text)) {
      flash("copied");
      return;
    }
    // 两条路都不通时至少把文本选中，用户按 ⌘C 还能拿走。
    const node = preRef.current;
    if (node) {
      const range = document.createRange();
      range.selectNodeContents(node);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    flash("failed");
  }, [text, flash]);

  const hint =
    state === "copied" ? "已复制" : state === "failed" ? "复制失败，已选中文本，请按 ⌘C" : "复制";

  return (
    <div className="group/cmd relative">
      {label ? (
        <p className="mb-1 font-mono text-[9.5px] uppercase tracking-wide" style={{ color: "var(--text-faint)" }}>
          {label}
        </p>
      ) : null}
      <pre
        ref={preRef}
        className="overflow-x-auto rounded-lg border px-2.5 py-2 pr-9 font-mono text-[11.5px] leading-relaxed"
        style={{
          background: "var(--bg-inset)",
          borderColor: "var(--border)",
          whiteSpace: wrap ? "pre-wrap" : "pre",
          wordBreak: wrap ? "break-word" : "normal",
        }}
      >
        {text}
      </pre>
      <button
        type="button"
        onClick={copy}
        aria-label={hint}
        title={hint}
        className="absolute right-1.5 grid h-6 w-6 place-items-center rounded-md border transition-opacity focus-visible:opacity-100 group-hover/cmd:opacity-100"
        style={{
          top: label ? 22 : 6,
          background: "var(--bg-elevated)",
          borderColor:
            state === "failed" ? "color-mix(in oklab, var(--color-warn-400) 55%, transparent)" : "var(--border)",
          color:
            state === "copied"
              ? "var(--color-ok-400)"
              : state === "failed"
                ? "var(--color-warn-400)"
                : "var(--text-faint)",
          // 反馈态必须一直可见：hover 才显示的失败提示等于没有提示。
          opacity: state === "idle" ? 0 : 1,
        }}
      >
        {state === "copied" ? (
          <CheckIcon size={12} weight="bold" />
        ) : state === "failed" ? (
          <WarningIcon size={12} weight="bold" />
        ) : (
          <CopyIcon size={12} />
        )}
      </button>
      {state === "failed" ? (
        <p className="mt-1 text-[10px]" style={{ color: "var(--text-warn)" }} role="status">
          浏览器拒绝了剪贴板写入。文本已选中，按 ⌘C / Ctrl+C 复制。
        </p>
      ) : null}
    </div>
  );
}
