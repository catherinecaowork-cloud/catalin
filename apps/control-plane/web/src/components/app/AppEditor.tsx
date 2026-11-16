import { Clock, Play } from "lucide-react";

import type { EditorTab, Worker } from "../../types";
import { MODULES } from "../../types";
import { parseRecTabId, parseRunTabId } from "../../utils/tabs";
import { ModuleToolbar, ModuleToolbarGroup, ModuleToolbarLabel } from "../patterns/ModuleToolbar";
import { EditorLayout, EditorPlaceholder, EditorView } from "../layout/EditorLayout";
import { StartPage } from "../layout/StartPage";
import { RecordEditorBody } from "../record/RecordEditorBody";
import { RunWorkspace } from "../run/RunWorkspace";
import { BottomPanel } from "../layout/BottomPanel";

type Props = {
  activeTab: EditorTab | null;
  activeRunId: string | null;
  activeRecRunId: string | null;
  workersOnline: boolean;
  workers: Worker[];
  lastHeaded: boolean;
  logLines: string[];
  logOpen: boolean;
  onClearLog: () => void;
  onToggleLog: () => void;
  onOpenRecord: () => void;
  onOpenRunModule: () => void;
  onOpenHistory: () => void;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  onFollowBatch: (runId: string, title: string) => void;
  onRunEnd?: () => void;
};

function ModulePlaceholder({ tab }: { tab: EditorTab }) {
  if (tab.kind === "run") {
    return (
      <EditorView
        toolbar={
          <ModuleToolbar color="var(--c-run)">
            <ModuleToolbarGroup>
              <ModuleToolbarLabel icon={Play}>选择流程并运行</ModuleToolbarLabel>
            </ModuleToolbarGroup>
          </ModuleToolbar>
        }
      >
        <EditorPlaceholder text="在左侧选中脚本，配置选项后启动回放。" />
      </EditorView>
    );
  }

  if (tab.kind === "history") {
    return (
      <EditorView
        toolbar={
          <ModuleToolbar color="var(--c-history)">
            <ModuleToolbarGroup>
              <ModuleToolbarLabel icon={Clock}>点击左侧记录打开详情</ModuleToolbarLabel>
            </ModuleToolbarGroup>
          </ModuleToolbar>
        }
      >
        <EditorPlaceholder text="从列表点一条运行记录，在主区域查看步骤与截图。" />
      </EditorView>
    );
  }

  return (
    <EditorView
      toolbar={
        <ModuleToolbar color={MODULES[tab.kind].color}>
          <ModuleToolbarGroup>
            <ModuleToolbarLabel>
              {MODULES[tab.kind].title} · {tab.title}
            </ModuleToolbarLabel>
          </ModuleToolbarGroup>
        </ModuleToolbar>
      }
    >
      <EditorPlaceholder text={MODULES[tab.kind].description} />
    </EditorView>
  );
}

export function AppEditor({
  activeTab,
  activeRunId,
  activeRecRunId,
  workersOnline,
  workers,
  lastHeaded,
  logLines,
  logOpen,
  onClearLog,
  onToggleLog,
  onOpenRecord,
  onOpenRunModule,
  onOpenHistory,
  onLog,
  onFollowBatch,
  onRunEnd,
}: Props) {
  const body = (() => {
    if (!activeTab) {
      return (
        <StartPage
          onOpenRecord={onOpenRecord}
          onOpenRun={onOpenRunModule}
          onOpenHistory={onOpenHistory}
        />
      );
    }

    const runId = activeRunId ?? parseRunTabId(activeTab.id);
    if (runId) {
      return (
        <RunWorkspace
          runId={runId}
          title={activeTab.title}
          workersOnline={workersOnline}
          workers={workers}
          headedRequested={lastHeaded}
          onLog={onLog}
          onFollowBatch={onFollowBatch}
          onRunEnd={onRunEnd}
        />
      );
    }

    if (activeTab.kind === "record") {
      return (
        <RecordEditorBody
          activeRecRunId={activeRecRunId ?? parseRecTabId(activeTab.id)}
          workersOnline={workersOnline}
          workers={workers}
          onLog={onLog}
        />
      );
    }

    return <ModulePlaceholder tab={activeTab} />;
  })();

  return (
    <EditorLayout
      footer={
        <BottomPanel
          lines={logLines}
          open={logOpen}
          onClear={onClearLog}
          onToggle={onToggleLog}
        />
      }
    >
      {body}
    </EditorLayout>
  );
}
