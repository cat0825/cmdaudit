/**
 * payload 载入。两种模式：
 *
 * - 生产：Python 把 JSON 写进 `<script id="cmdaudit-payload" type="application/json">`，
 *   同步解析，页面首帧就有真数据；
 * - 开发：读 `public/fixture.json`（由 `cmdaudit viz --emit-fixture` 生成的真实聚合）。
 *
 * 两种模式共用同一个解析出口，避免开发态和产物态跑在不同代码路径上。
 */
import { EMPTY_PAYLOAD, type Payload } from "./payload";

const PAYLOAD_ELEMENT_ID = "cmdaudit-payload";

export type LoadState =
  | { status: "ready"; payload: Payload; source: "embedded" | "fixture" }
  | { status: "loading" }
  | { status: "error"; message: string };

export function readEmbeddedPayload(): Payload | null {
  const node = document.getElementById(PAYLOAD_ELEMENT_ID);
  if (!node?.textContent) return null;
  const trimmed = node.textContent.trim();
  // Python 侧未注入时留的占位符，不当成数据。
  if (!trimmed || trimmed === "null" || trimmed.startsWith("__CMDAUDIT")) return null;
  const parsed = JSON.parse(trimmed) as Partial<Payload>;
  return { ...EMPTY_PAYLOAD, ...parsed };
}

export async function loadFixture(): Promise<Payload> {
  const response = await fetch("fixture.json");
  if (!response.ok) throw new Error(`fixture.json ${response.status}`);
  const parsed = (await response.json()) as Partial<Payload>;
  return { ...EMPTY_PAYLOAD, ...parsed };
}
