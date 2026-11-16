import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AppEditor } from "./components/app/AppEditor";
import { ExplorerSidebar } from "./components/app/ExplorerSidebar";
import { AiConfigModal } from "./components/AiConfigModal";
import { RecordWebModal } from "./components/record/RecordWebModal";
import { MainToolbar } from "./components/layout/MainToolbar";
import { TitleBar } from "./components/layout/TitleBar";
import { Workbench } from "./components/layout/Workbench";
import { TabStrip } from "./components/TabStrip";
import { WorkerBar } from "./components/WorkerBar";
import { HistoryProvider, useHistoryContext } from "./context/HistoryContext";
import { RecordProvider } from "./context/RecordContext";
import { RunProvider, useRunContext } from "./context/RunContext";
import { useAiConfig } from "./hooks/useAiConfig";
import { useLog } from "./hooks/useLog";
import { useSites } from "./hooks/useSites";
import { useWorker } from "./hooks/useWorker";
import type { EditorTab, ModuleKind } from "./types";
import {
  isModuleTab,
  newTabId,
  openTabTitle,
  parseRecTabId,
  parseRunTabId,
  recTabId,
  runTabId,
} from "./utils/tabs";

type WorkbenchProps = {
  logOpen: boolean;
  onToggleLog: () => void;
  onClearLog: () => void;
  logLines: string[];
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

function RecordProviderWithFlowSync({
  sitesState,
  children,
  ...recordProps
}: {
  sitesState: ReturnType<typeof useSites>;
  children: ReactNode;
  siteId: string | null;
  siteCredentials: ReturnType<typeof useSites>["credentials"];
  workers: ReturnType<typeof useWorker>["workers"];
  onLog: WorkbenchProps["onLog"];
  onOpenRecordTab: (runId: string, title: string) => void;
  onRequestAiConfig: () => void;
}) {
  const { refresh, setSelectedFlowId } = useRunContext();

  const onFlowSaved = useCallback(
    ({ siteId: savedSiteId, flowId }: { siteId: string; flowId: string; flowName: string }) => {
      if (savedSiteId !== sitesState.selectedSiteId) {
        sitesState.setSelectedSiteId(savedSiteId);
      } else {
        void refresh();
      }
      setSelectedFlowId(flowId);
    },
    [refresh, setSelectedFlowId, sitesState.selectedSiteId, sitesState.setSelectedSiteId],
  );

  return (
    <RecordProvider {...recordProps} onFlowSaved={onFlowSaved}>
      {children}
    </RecordProvider>
  );
}

function AppWorkbenchBody({
  logOpen,
  onToggleLog,
  onClearLog,
  logLines,
  onLog,
  sitesState,
}: WorkbenchProps & { sitesState: ReturnType<typeof useSites> }) {
  const worker = useWorker(onLog);
  const ai = useAiConfig(onLog);
  const { notifyRunFinished } = useHistoryContext();
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [editorTabs, setEditorTabs] = useState<EditorTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [lastHeaded, setLastHeaded] = useState(false);

  useEffect(() => {
    if (sitesState.error) onLog(`站点加载失败：${sitesState.error}`, "error");
  }, [sitesState.error, onLog]);

  const activeTab = useMemo(
    () => editorTabs.find((tab) => tab.id === activeTabId) ?? null,
    [editorTabs, activeTabId],
  );

  const activeRunId = activeTab ? parseRunTabId(activeTab.id) : null;
  const activeRecRunId = activeTab ? parseRecTabId(activeTab.id) : null;

  const openModule = useCallback(
    (kind: ModuleKind) => {
      const existing = editorTabs.find((tab) => tab.kind === kind && isModuleTab(tab.id));
      if (existing) {
        setActiveTabId(existing.id);
        if (kind === "log") onToggleLog();
        return;
      }
      const tab: EditorTab = { id: newTabId(kind), kind, title: openTabTitle(kind) };
      setEditorTabs((prev) => [...prev, tab]);
      setActiveTabId(tab.id);
      if (kind === "log") onToggleLog();
    },
    [editorTabs, onToggleLog],
  );

  const openRunTab = useCallback((runId: string, title: string, headed = false) => {
    const tabId = runTabId(runId);
    setLastHeaded(headed);
    setEditorTabs((prev) => {
      if (prev.some((tab) => tab.id === tabId)) return prev;
      return [...prev, { id: tabId, kind: "run", title }];
    });
    setActiveTabId(tabId);
  }, []);

  const openRecordTab = useCallback((runId: string, title: string) => {
    const tabId = recTabId(runId);
    setLastHeaded(true);
    setEditorTabs((prev) => {
      if (prev.some((tab) => tab.id === tabId)) return prev;
      return [...prev, { id: tabId, kind: "record", title }];
    });
    setActiveTabId(tabId);
  }, []);

  const closeTab = useCallback(
    (tabId: string) => {
      setEditorTabs((prev) => {
        const next = prev.filter((tab) => tab.id !== tabId);
        if (activeTabId === tabId) {
          setActiveTabId(next[0]?.id ?? null);
        }
        return next;
      });
    },
    [activeTabId],
  );

  return (
    <RunProvider siteId={sitesState.selectedSiteId} sites={sitesState.sites} onLog={onLog}>
      <RecordProviderWithFlowSync
        sitesState={sitesState}
        siteId={sitesState.selectedSiteId}
        siteCredentials={sitesState.credentials}
        workers={worker.workers}
        onLog={onLog}
        onOpenRecordTab={openRecordTab}
        onRequestAiConfig={() => void ai.openModal()}
      >
        <TitleBar
          tabs={
            <TabStrip
              tabs={editorTabs}
              activeTabId={activeTabId}
              onSelect={setActiveTabId}
              onClose={closeTab}
            />
          }
          toolbar={
            <MainToolbar
              sitesState={sitesState}
              onLog={onLog}
              onLaunchRecord={() => setRecordModalOpen(true)}
              onOpenRun={() => openModule("run")}
            />
          }
          status={
            <WorkerBar
              badge={worker.badge}
              phase={worker.phase}
              online={worker.online}
              busy={worker.busy}
              aiBadge={ai.badge}
              onStart={() => void worker.start()}
              onStop={() => void worker.stop()}
              onOpenAiConfig={() => void ai.openModal()}
              onToggleLog={onToggleLog}
              logOpen={logOpen}
            />
          }
        />

        <Workbench
          sidebar={
            <ExplorerSidebar
              siteName={sitesState.selectedSite?.name ?? null}
              onOpenRun={openRunTab}
              onOpenRunModule={() => openModule("run")}
              onRefreshWorkers={() => void worker.refresh()}
            />
          }
          editor={
            <AppEditor
              activeTab={activeTab}
              activeRunId={activeRunId}
              activeRecRunId={activeRecRunId}
              workersOnline={worker.online}
              workers={worker.workers}
              lastHeaded={lastHeaded}
              logLines={logLines}
              logOpen={logOpen}
              onClearLog={onClearLog}
              onToggleLog={onToggleLog}
              onOpenRecord={() => setRecordModalOpen(true)}
              onOpenRunModule={() => openModule("run")}
              onOpenHistory={() => openModule("history")}
              onOpenRunRecord={openRunTab}
              onLog={onLog}
              onFollowBatch={(runId, title) => openRunTab(runId, title, lastHeaded)}
              onRunEnd={notifyRunFinished}
            />
          }
        />

        <RecordWebModal
          open={recordModalOpen}
          onClose={() => setRecordModalOpen(false)}
          sites={sitesState.sites}
          selectedSiteId={sitesState.selectedSiteId}
          onSelectSite={sitesState.setSelectedSiteId}
          onCreateSite={sitesState.createSite}
          onUpdateSite={sitesState.updateSite}
          onDeleteSite={sitesState.deleteSite}
          onSaveFormLogin={(site, path, username, password) =>
            sitesState.saveFormLogin(site, path, username, password, onLog)
          }
          onDeleteCredential={sitesState.deleteCredential}
          onLog={onLog}
        />

        <AiConfigModal ai={ai} />
      </RecordProviderWithFlowSync>
    </RunProvider>
  );
}

function AppWorkbench(props: WorkbenchProps) {
  const sitesState = useSites();
  return (
    <HistoryProvider siteId={sitesState.selectedSiteId} onLog={props.onLog}>
      <AppWorkbenchBody {...props} sitesState={sitesState} />
    </HistoryProvider>
  );
}

export default function App() {
  const { lines, open, append, clear, toggle } = useLog();

  const onLog = useCallback(
    (message: string, level?: "info" | "warn" | "error") => {
      append(message, level);
    },
    [append],
  );

  const onToggleLog = useCallback(() => {
    toggle();
  }, [toggle]);

  return (
    <AppWorkbench
      logOpen={open}
      onToggleLog={onToggleLog}
      onClearLog={clear}
      logLines={lines}
      onLog={onLog}
    />
  );
}
