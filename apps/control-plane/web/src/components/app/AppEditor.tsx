import type { EditorTab, Worker } from "../../types";
import { MODULES } from "../../types";
import { parseRecTabId, parseRunTabId } from "../../utils/tabs";
import { EditorEmpty, EditorLayout, EditorPlaceholder, EditorView } from "../layout/EditorLayout";
import { RecordEditorBody } from "../record/RecordEditorBody";
import { RunWorkspace } from "../run/RunWorkspace";
import { BottomLog } from "../BottomLog";

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
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  onFollowBatch: (runId: string, title: string) => void;
  onRunEnd?: () => void;
};

function ModulePlaceholder({ tab }: { tab: EditorTab }) {
  if (tab.kind === "run") {
    return (
      <EditorView toolbar="运行 · 选择流程并点击「运行所选流程」" color="var(--c-run)">
        <EditorPlaceholder text="在左侧选中脚本，配置选项后启动回放。" />
      </EditorView>
    );
  }

  if (tab.kind === "history") {
    return (
      <EditorView toolbar="历史 · 点击左侧记录打开详情" color="var(--c-history)">
        <EditorPlaceholder text="从列表点一条运行记录，在主区域查看步骤与截图。" />
      </EditorView>
    );
  }

  return (
    <EditorView
      toolbar={`${MODULES[tab.kind].title} · ${tab.title}`}
      color={MODULES[tab.kind].color}
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
  onLog,
  onFollowBatch,
  onRunEnd,
}: Props) {
  const body = (() => {
    if (!activeTab) {
      return (
        <EditorEmpty
          title="自动化测试平台"
          subtitle="React 控制台"
          hint="先选站点，再打开录制、运行或历史。"
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
    <EditorLayout footer={<BottomLog lines={logLines} open={logOpen} onClear={onClearLog} />}>
      {body}
    </EditorLayout>
  );
}
