/**
 * 本地处理状态层。
 *
 * 这里存的是**人的判断**（状态、负责人、备注），不是证据。
 * 它与 `commands.duckdb` 严格分离：证据只读，判断只写 localStorage。
 * 因此清空浏览器存储只会丢失流转记录，不会影响任何统计数字。
 *
 * key 里带 source_db 指纹，换一个数据库不会串用上一个库的状态。
 */

export const TRIAGE_STATUSES = ["open", "reviewing", "verified", "dismissed"] as const;
export type TriageStatus = (typeof TRIAGE_STATUSES)[number];

export const STATUS_LABEL: Record<TriageStatus, string> = {
  open: "待处理",
  reviewing: "排查中",
  verified: "已确认",
  dismissed: "已排除",
};

export interface TriageEntry {
  status: TriageStatus;
  owner: string;
  note: string;
  updated_at: string;
}

export type TriageMap = Record<string, TriageEntry>;

const VERSION = "v1";

function storageKey(sourceDb: string): string {
  // 只取路径末段，避免把完整本机路径写进存储键。
  const leaf = sourceDb.split("/").pop() ?? "db";
  return `cmdaudit.triage.${VERSION}.${leaf}`;
}

function isStatus(value: unknown): value is TriageStatus {
  return typeof value === "string" && (TRIAGE_STATUSES as readonly string[]).includes(value);
}

export function loadTriage(sourceDb: string): TriageMap {
  try {
    const raw = window.localStorage.getItem(storageKey(sourceDb));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: TriageMap = {};
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value !== "object" || value === null) continue;
      const entry = value as Record<string, unknown>;
      if (!isStatus(entry.status)) continue;
      result[id] = {
        status: entry.status,
        owner: typeof entry.owner === "string" ? entry.owner : "",
        note: typeof entry.note === "string" ? entry.note : "",
        updated_at: typeof entry.updated_at === "string" ? entry.updated_at : "",
      };
    }
    return result;
  } catch {
    // localStorage 在 file:// 下可能被策略禁用；此时降级为纯只读浏览。
    return {};
  }
}

export function saveTriage(sourceDb: string, map: TriageMap): void {
  try {
    window.localStorage.setItem(storageKey(sourceDb), JSON.stringify(map));
  } catch {
    /* 存储不可用时静默降级，不打断浏览 */
  }
}

export function entryFor(map: TriageMap, id: string): TriageEntry {
  return map[id] ?? { status: "open", owner: "", note: "", updated_at: "" };
}
