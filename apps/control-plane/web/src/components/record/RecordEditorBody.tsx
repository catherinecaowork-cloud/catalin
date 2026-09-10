import { CircleDot } from "lucide-react";

import { useRecordContext } from "../../context/RecordContext";
import type { Worker } from "../../types";
import { ModuleToolbar, ModuleToolbarGroup, ModuleToolbarLabel } from "../patterns/ModuleToolbar";
import { EditorPlaceholder, EditorView } from "../layout/EditorLayout";
import { RecordDraftWorkspace } from "./RecordDraftWorkspace";

type Props = {
  activeRecRunId: string | null;
  workersOnline: boolean;
  workers: Worker[];
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function RecordEditorBody({ onLog: _onLog }: Props) {
  const ctx = useRecordContext();

  if (ctx.stage === "result" && ctx.draftSteps.length) {
    return <RecordDraftWorkspace />;
  }

  if (ctx.stage === "busy") {
    return (
      <EditorView
        toolbar={
          <ModuleToolbar color="var(--c-record)">
            <ModuleToolbarGroup>
              <ModuleToolbarLabel icon={CircleDot}>Web 录制</ModuleToolbarLabel>
            </ModuleToolbarGroup>
          </ModuleToolbar>
        }
      >
        <div className="record-live-workspace">
          <EditorPlaceholder text="浏览器窗口已打开，请在页面中操作。" />
          <p className="record-live-workspace-hint muted">
            Web 录制面板会自动出现在浏览器窗口右侧（Katalon 风格），实时列出每个动作。完成后点击浏览器旁录制窗口或顶栏的「停止」。
          </p>
        </div>
      </EditorView>
    );
  }

  return (
    <EditorView
      toolbar={
        <ModuleToolbar color="var(--c-record)">
          <ModuleToolbarGroup>
            <ModuleToolbarLabel icon={CircleDot}>Web 录制</ModuleToolbarLabel>
          </ModuleToolbarGroup>
        </ModuleToolbar>
      }
    >
      <EditorPlaceholder text="点击顶栏「录制」按钮，输入 URL 后开始开窗录制。" />
    </EditorView>
  );
}
