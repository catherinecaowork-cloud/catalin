import type { RecordStep } from "../../types";
import { EmptyState, ModuleHint } from "../ui";
import type { DraftStepPatch } from "./DraftStepGrid";
import { DraftStepGrid } from "./DraftStepGrid";

type Props = {
  steps: RecordStep[];
  onUpdate: (index: number, patch: DraftStepPatch) => void;
  onDelete: (index: number) => void;
  onMakeUniqueValue: (index: number) => void;
};

export function DraftStepList({ steps, onUpdate, onDelete, onMakeUniqueValue }: Props) {
  return (
    <div className="draft-steps-pane">
      <ModuleHint>步骤在这里滚动查看。连续重复点击已合并。</ModuleHint>
      {steps.length === 0 ? (
        <EmptyState>还没有步骤。</EmptyState>
      ) : (
        <DraftStepGrid
          steps={steps}
          onUpdate={onUpdate}
          onDelete={onDelete}
          onMakeUniqueValue={onMakeUniqueValue}
        />
      )}
    </div>
  );
}
