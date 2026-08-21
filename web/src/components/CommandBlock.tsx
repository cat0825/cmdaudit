/**
 * 命令原文 / SQL 展示块。
 * 命令原文是外部数据，这里只作为文本节点渲染（React 默认转义），不用 dangerouslySetInnerHTML。
 */
import { useCallback, useState } from "react";
import { CheckIcon, CopyIcon } from "@phosphor-icons/react";

export function CommandBlock({
  text,
  label,
  wrap = false,
}: {
  text: string;
  label?: string;
  wrap?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    // file:// 下 clipboard API 可能不可用，退回 execCommand，再失败就只置灰。
    const done = () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => undefined);
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    try {
      document.execCommand("copy");
      done();
    } finally {
      area.remove();
    }
  }, [text]);

  return (
    <div className="group/cmd relative">
      {label ? (
        <p className="mb-1 font-mono text-[9.5px] uppercase tracking-wide" style={{ color: "var(--text-faint)" }}>
          {label}
        </p>
      ) : null}
      <pre
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
        aria-label="复制"
        className="absolute right-1.5 grid h-6 w-6 place-items-center rounded-md border opacity-0 transition-opacity group-hover/cmd:opacity-100 focus-visible:opacity-100"
        style={{
          top: label ? 22 : 6,
          background: "var(--bg-elevated)",
          borderColor: "var(--border)",
          color: copied ? "var(--color-ok-400)" : "var(--text-faint)",
        }}
      >
        {copied ? <CheckIcon size={12} weight="bold" /> : <CopyIcon size={12} />}
      </button>
    </div>
  );
}
