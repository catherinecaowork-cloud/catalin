import { useCallback, useEffect, useMemo, useState } from "react";



import { AppEditor } from "./components/app/AppEditor";

import { AppSidebar } from "./components/app/AppSidebar";

import { AiConfigModal } from "./components/AiConfigModal";

import { ActivityBar } from "./components/layout/ActivityBar";

import { TitleBar } from "./components/layout/TitleBar";

import { Workbench } from "./components/layout/Workbench";

import { SiteChip } from "./components/SiteChip";

import { TabStrip } from "./components/TabStrip";

import { WorkerBar } from "./components/WorkerBar";

import { HistoryProvider, useHistoryContext } from "./context/HistoryContext";

import { RecordProvider } from "./context/RecordContext";

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

  const [menuOpen, setMenuOpen] = useState(false);

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

    <RecordProvider

      siteId={sitesState.selectedSiteId}

      siteCredentials={sitesState.credentials}

      workers={worker.workers}

      onLog={onLog}

      onOpenRecordTab={openRecordTab}

      onRequestAiConfig={() => void ai.openModal()}

    >

      <TitleBar

        site={

          <SiteChip

            sites={sitesState.sites}

            selectedSiteId={sitesState.selectedSiteId}

            credentials={sitesState.credentials}

            credsLoading={sitesState.credsLoading}

            open={menuOpen}

            onToggle={() => setMenuOpen((open) => !open)}

            onClose={() => setMenuOpen(false)}

            onSelect={(siteId) => {

              sitesState.setSelectedSiteId(siteId);

              setMenuOpen(false);

              onLog(

                `已切换站点：${sitesState.sites.find((s) => s.id === siteId)?.name ?? siteId}`,

              );

            }}

            onRefresh={() => void sitesState.refresh()}

            onCreateSite={sitesState.createSite}

            onDeleteSite={sitesState.deleteSite}

            onDeleteCredential={(credentialId) => {

              if (!sitesState.selectedSiteId) return Promise.resolve();

              return sitesState.deleteCredential(sitesState.selectedSiteId, credentialId);

            }}

            onSaveLogin={(path, username, password) => {

              if (!sitesState.selectedSite) return Promise.resolve();

              return sitesState.saveFormLogin(

                sitesState.selectedSite,

                path,

                username,

                password,

                onLog,

              );

            }}

            onLog={onLog}

          />

        }

        tabs={

          <TabStrip

            tabs={editorTabs}

            activeTabId={activeTabId}

            onSelect={setActiveTabId}

            onClose={closeTab}

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

          />

        }

      />



      <Workbench

        activity={<ActivityBar activeKind={activeTab?.kind ?? null} onOpen={openModule} />}

        sidebar={

          <AppSidebar

            activeTab={activeTab}

            siteId={sitesState.selectedSiteId}

            sites={sitesState.sites}

            onLog={onLog}

            onOpenRun={openRunTab}

            onRefreshWorkers={() => void worker.refresh()}

            onToggleLog={onToggleLog}

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

            onLog={onLog}

            onFollowBatch={(runId, title) => openRunTab(runId, title, lastHeaded)}

            onRunEnd={notifyRunFinished}

          />

        }

      />



      <AiConfigModal ai={ai} />

    </RecordProvider>

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


