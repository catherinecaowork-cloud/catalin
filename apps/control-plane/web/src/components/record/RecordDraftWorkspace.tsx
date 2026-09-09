import { useRecordContext } from "../../context/RecordContext";
import { EditorView } from "../layout/EditorLayout";
import { DraftStepList } from "./DraftStepList";

export function RecordDraftWorkspace() {
  const ctx = useRecordContext();

  return (
    <EditorView toolbar="录制 · 确认步骤" color="var(--c-record)" bodyClassName="draft-workspace">
      <DraftStepList
        steps={ctx.draftSteps}
        onUpdate={(index, patch) => ctx.updateStep(index, patch)}
        onDelete={(index) => ctx.deleteStep(index)}
        onMakeUniqueValue={(index) => ctx.setStepUniqueValue(index)}
      />
    </EditorView>
  );
}
