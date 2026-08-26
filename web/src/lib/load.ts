/**
 * payload 载入。两种模式：
 *
 * - 生产：Python 把 JSON 写进 `<script id="cmdaudit-payload" type="application/json">`，
 *   同步解析，页面首帧就有真数据；
 * - 开发：读 `public/fixture.json`（由 `cmdaudit viz --emit-fixture` 生成的真实聚合）。
 *
 * 两种模式共用同一个解析出口，避免开发态和产物态跑在不同代码路径上。
 * 出口一律过 `sanitizePayload`：产物是可被手改、可由旧版 Python 生成的单文件 HTML，
 * 「同源生成」不构成免验证的理由。
 */
import type { Payload } from "./payload";
import { sanitizePayload, type SanitizeResult } from "./sanitize";

const PAYLOAD_ELEMENT_ID = "cmdaudit-payload";

export type LoadState =
  | { status: "ready"; payload: Payload; source: "embedded" | "fixture" }
  | { status: "loading" }
  | { status: "error"; message: string };

export function readEmbeddedPayload(): SanitizeResult | null {
  const node = document.getElementById(PAYLOAD_ELEMENT_ID);
  if (!node?.textContent) return null;
  const trimmed = node.textContent.trim();
  // Python 侧未注入时留的占位符，不当成数据。
  if (!trimmed || trimmed === "null" || trimmed.startsWith("__CMDAUDIT")) return null;
  return sanitizePayload(JSON.parse(trimmed));
}

export async function loadFixture(): Promise<SanitizeResult> {
  const response = await fetch("fixture.json");
  if (!response.ok) throw new Error(`fixture.json ${response.status}`);
  return sanitizePayload(await response.json());
}
