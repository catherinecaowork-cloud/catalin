import { FileText, RefreshCw, Save, Sparkles } from "lucide-react";

import { useRecordContext } from "../../context/RecordContext";
import {
  ModuleToolbar,
  ModuleToolbarBadge,
  ModuleToolbarButton,
  ModuleToolbarGroup,
  ModuleToolbarLabel,
  ModuleToolbarSep,
  ModuleToolbarSpacer,
} from "../patterns/ModuleToolbar";
import { EditorView } from "../layout/EditorLayout";
import { DraftStepList } from "./DraftStepList";
import { RecordSidebarFoot } from "./RecordSidebar";

export function RecordDraftWorkspace() {
  const ctx = useRecordContext();
  const canToggleScripts = ctx.sampleSteps.length > 0 && ctx.observerSteps.length > 0;

  const toolbar = (
    <ModuleToolbar color="var(--c-record)">
      <ModuleToolbarGroup>
        <ModuleToolbarLabel icon={Sparkles}>确认步骤</ModuleToolbarLabel>
        <ModuleToolbarBadge>{ctx.compilePath}</ModuleToolbarBadge>
      </ModuleToolbarGroup>
      {canToggleScripts ? (
        <>
          <ModuleToolbarSep />
          <ModuleToolbarGroup>
            <ModuleToolbarButton
              icon={Sparkles}
              label="观察者"
              active={ctx.scriptSource === "observer"}
              onClick={() => ctx.switchScriptSource("observer")}
            />
            <ModuleToolbarButton
              icon={FileText}
              label="样例"
              active={ctx.scriptSource === "sample"}
              onClick={() => ctx.switchScriptSource("sample")}
            />
          </ModuleToolbarGroup>
        </>
      ) : null}
      <ModuleToolbarSpacer />
      <ModuleToolbarGroup>
        <ModuleToolbarButton
          icon={RefreshCw}
          title="重新观察者编写"
          onClick={() => void ctx.retryCompile()}
        />
        <ModuleToolbarButton
          icon={Save}
          title="保存为流程"
          disabled={!ctx.draftSteps.length}
          onClick={() => void ctx.saveRecord()}
        />
      </ModuleToolbarGroup>
    </ModuleToolbar>
  );

  return (
    <EditorView toolbar={toolbar} bodyClassName="draft-workspace">
      <div className="draft-workspace-split">
        <DraftStepList
          steps={ctx.draftSteps}
          onUpdate={(index, patch) => ctx.updateStep(index, patch)}
          onDelete={(index) => ctx.deleteStep(index)}
          onMoveUp={(index) => ctx.moveStepUp(index)}
          onMoveDown={(index) => ctx.moveStepDown(index)}
          onAdd={(action, afterIndex) => ctx.addDraftStep(action, afterIndex)}
          onMakeUniqueValue={(index) => ctx.setStepUniqueValue(index)}
        />
        <aside className="record-save-panel">
          <RecordSidebarFoot />
        </aside>
      </div>
    </EditorView>
  );
}
