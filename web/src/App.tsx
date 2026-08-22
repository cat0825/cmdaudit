/** 工作台外壳：视图切换、抽屉、⌘K、处理状态持久化都汇总在这里。 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Payload } from "./lib/payload";
import { Rail } from "./components/Rail";
import { Topbar } from "./components/Topbar";
import { DetailDrawer } from "./components/DetailDrawer";
import { CommandPalette } from "./components/CommandPalette";
import { OverviewView } from "./views/OverviewView";
import { QueueView } from "./views/QueueView";
import { BoardView } from "./views/BoardView";
import { DurationView, EvidenceView } from "./views/TrackView";
import { CandidatesView } from "./views/CandidatesView";
import { isViewId, VIEWS, type ViewId } from "./lib/views";
import { useTheme } from "./lib/theme";
import { VIEW_FADE } from "./lib/motion";
import {
  entryFor,
  loadTriage,
  saveTriage,
  type TriageEntry,
  type TriageMap,
  type TriageStatus,
} from "./lib/triage";

function initialView(): ViewId {
  const hash = window.location.hash.replace(/^#/, "");
  return isViewId(hash) ? hash : "overview";
}

export function App({ payload }: { payload: Payload }) {
  const [view, setView] = useState<ViewId>(initialView);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [triage, setTriage] = useState<TriageMap>(() => loadTriage(payload.source_db));
  const theme = useTheme();

  useEffect(() => {
    saveTriage(payload.source_db, triage);
  }, [payload.source_db, triage]);

  // hash 同步：刷新后停在同一视图，也让浏览器前进/后退可用。
  useEffect(() => {
    window.location.hash = view;
  }, [view]);

  // 选中项是队列视图的局部状态：切走即清空。否则在 Board/总览按 1–4
  // 时，window 级 handler 会用 activeId 改写一条看不见的队列记录，
  // 造成「一条在队列、一条在看板」的两处修改。
  useEffect(() => {
    if (view !== "queue") setSelectedId(null);
  }, [view]);
  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace(/^#/, "");
      if (isViewId(hash)) setView(hash);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const findingIndex = useMemo(
    () => new Map(payload.findings.map((finding) => [finding.finding_id, finding])),
    [payload.findings],
  );

  const patch = useCallback((ids: string[], next: Partial<TriageEntry>) => {
    setTriage((current) => {
      const draft = { ...current };
      const stamp = new Date().toISOString();
      for (const id of ids) {
        draft[id] = { ...entryFor(current, id), ...next, updated_at: stamp };
      }
      return draft;
    });
  }, []);

  const openFinding = useCallback(
    (findingId: string) => {
      setSelectedId(findingId);
      setOpenId(findingId);
      if (!findingIndex.has(findingId)) setOpenId(null);
    },
    [findingIndex],
  );

  // 全局快捷键：⌘K 面板、Esc 收起、1..4 给当前选中项打状态。
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
        return;
      }
      if (event.key === "Escape") {
        if (paletteOpen) setPaletteOpen(false);
        else if (openId) setOpenId(null);
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      const statuses: TriageStatus[] = ["open", "reviewing", "verified", "dismissed"];
      const slot = Number.parseInt(event.key, 10);
      const activeId = openId ?? selectedId;
      if (activeId && slot >= 1 && slot <= statuses.length && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        patch([activeId], { status: statuses[slot - 1]! });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [paletteOpen, openId, selectedId, patch]);

  const openCount = useMemo(
    () => payload.findings.filter((finding) => entryFor(triage, finding.finding_id).status === "open").length,
    [payload.findings, triage],
  );

  const counts: Partial<Record<ViewId, number>> = {
    queue: openCount,
    board: payload.findings.length,
    candidates: payload.candidates.length,
  };

  const commandTotal = typeof payload.coverage["命令总数"] === "number" ? payload.coverage["命令总数"] : 0;
  const openFindingObject = openId ? (findingIndex.get(openId) ?? null) : null;

  return (
    <div className="min-h-[100dvh] lg:grid lg:grid-cols-[214px_minmax(0,1fr)]">
      <div className="sticky top-0 hidden h-[100dvh] lg:block">
        <Rail
          active={view}
          onSelect={setView}
          counts={counts}
          sourceDb={payload.source_db}
          commandTotal={commandTotal}
        />
      </div>

      <div className="min-w-0">
        <Topbar
          view={view}
          generatedAt={payload.generated_at}
          latestEventAt={payload.dashboard.latest_event_at}
          themeChoice={theme.choice}
          onThemeChange={theme.setChoice}
          onOpenPalette={() => setPaletteOpen(true)}
        />

        {/* 窄屏导航：轨道换成横向滚动条，不做汉堡菜单 —— 六个视图值得常驻可见。
            渲染中文 label 而不是内部路由 id，可访问名称才有意义。 */}
        <nav
          className="sticky top-[60px] z-10 flex gap-1 overflow-x-auto border-b px-4 py-2 lg:hidden"
          style={{ borderColor: "var(--border)", background: "var(--bg)" }}
        >
          {VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setView(item.id)}
              aria-current={view === item.id ? "page" : undefined}
              className="shrink-0 rounded-lg border px-2.5 py-1 text-[11.5px]"
              style={{
                borderColor: view === item.id ? "color-mix(in oklab, var(--color-accent-400) 42%, transparent)" : "var(--border)",
                color: view === item.id ? "var(--color-accent-500)" : "var(--text-muted)",
                background: view === item.id ? "color-mix(in oklab, var(--color-accent-400) 10%, transparent)" : "transparent",
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <main className="px-4 pb-16 pt-4 sm:px-6">
          <AnimatePresence mode="wait">
            <motion.div key={view} variants={VIEW_FADE} initial="hidden" animate="visible" exit="exit">
              {view === "overview" ? (
                <OverviewView payload={payload} onNavigate={setView} onOpenFinding={openFinding} />
              ) : null}
              {view === "queue" ? (
                <QueueView
                  payload={payload}
                  triage={triage}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onOpen={openFinding}
                  onPatchMany={patch}
                />
              ) : null}
              {view === "board" ? (
                <BoardView
                  payload={payload}
                  triage={triage}
                  onOpen={openFinding}
                  onSetStatus={(id, status) => patch([id], { status })}
                />
              ) : null}
              {view === "duration" ? <DurationView payload={payload} /> : null}
              {view === "candidates" ? <CandidatesView payload={payload} /> : null}
              {view === "evidence" ? <EvidenceView payload={payload} /> : null}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <DetailDrawer
        finding={openFindingObject}
        entry={entryFor(triage, openId ?? "")}
        jumpEnabled={view === "queue"}
        onClose={() => setOpenId(null)}
        onPatch={(next) => {
          if (openId) patch([openId], next);
        }}
      />

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        findings={payload.findings}
        onNavigate={setView}
        onOpenFinding={(findingId) => {
          setView("queue");
          openFinding(findingId);
        }}
        onThemeChange={theme.setChoice}
      />
    </div>
  );
}
