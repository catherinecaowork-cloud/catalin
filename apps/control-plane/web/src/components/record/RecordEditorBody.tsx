import { useRecordContext } from "../../context/RecordContext";
import type { Worker } from "../../types";
import { EditorPlaceholder, EditorView } from "../layout/EditorLayout";
import { RunWorkspace } from "../run/RunWorkspace";
import { RecordDraftWorkspace } from "./RecordDraftWorkspace";

type Props = {
  activeRecRunId: string | null;
  workersOnline: boolean;
  workers: Worker[];
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function RecordEditorBody({ activeRecRunId, workersOnline, workers, onLog }: Props) {
  const ctx = useRecordContext();
  const liveRunId =
    ctx.stage === "busy" && ctx.recordRunId
      ? activeRecRunId && activeRecRunId !== ctx.recordRunId
        ? activeRecRunId
        : ctx.recordRunId
      : activeRecRunId;

  if (ctx.stage === "result" && ctx.draftSteps.length) {
    return <RecordDraftWorkspace />;
  }

  if (liveRunId && ctx.stage === "busy") {
    return (
      <RunWorkspace
        runId={liveRunId}
        title={`录制 · ${liveRunId.slice(0, 8)}`}
        moduleColor="var(--c-record)"
        workersOnline={workersOnline}
        workers={workers}
        headedRequested
        onLog={onLog}
      />
    );
  }

  return (
    <EditorView toolbar="录制 · 填写意图后开始" color="var(--c-record)">
      <EditorPlaceholder text="开窗录制业务操作，结束后 AI 编译或直接保存为草稿。" />
    </EditorView>
  );
}
