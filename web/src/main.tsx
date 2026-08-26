import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./App";
import { EMPTY_PAYLOAD } from "./lib/payload";
import { loadFixture, readEmbeddedPayload } from "./lib/load";
import type { SanitizeResult } from "./lib/sanitize";

const container = document.getElementById("root");
if (!container) throw new Error("#root missing");
const root = createRoot(container);

function fail(message: string): void {
  root.render(
    <div style={{ padding: "48px", fontFamily: "system-ui", fontSize: 13, lineHeight: 1.7 }}>
      <p style={{ fontWeight: 600, marginBottom: 6 }}>数据载入失败</p>
      <p style={{ opacity: 0.7 }}>{message}</p>
      <p style={{ opacity: 0.7 }}>请重新运行 cmdaudit viz 生成页面。</p>
    </div>,
  );
}

function mount({ payload, warnings }: SanitizeResult): void {
  root.render(
    <StrictMode>
      <App payload={payload} loadWarnings={warnings} />
    </StrictMode>,
  );
}

try {
  const embedded = readEmbeddedPayload();
  if (embedded) {
    mount(embedded);
  } else {
    // 开发态：无注入 payload 时读 fixture（真实聚合导出），不用假数据。
    loadFixture()
      .then(mount)
      .catch(() => {
        if (import.meta.env.DEV) mount({ payload: EMPTY_PAYLOAD, warnings: [] });
        else fail("页面里没有找到内嵌 payload。");
      });
  }
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
