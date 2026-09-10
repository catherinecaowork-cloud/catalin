import type { RecordStep } from "../../types";
import { EmptyState, ModuleHint } from "../ui";
import type { DraftStepPatch } from "./DraftStepGrid";
import { DraftStepGrid } from "./DraftStepGrid";

type Props = {
  steps: RecordStep[];
  onUpdate: (index: number, patch: DraftStepPatch) => void;
  onDelete: (index: number) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onAdd: (action: string, afterIndex?: number) => void;
  onMakeUniqueValue: (index: number) => void;
};

export function DraftStepList({
  steps,
  onUpdate,
  onDelete,
  onMoveUp,
  onMoveDown,
  onAdd,
  onMakeUniqueValue,
}: Props) {
  return (
    <div className="draft-steps-pane">
      <ModuleHint>点击行选中，用上方控制台调整顺序、删除或新增步骤。</ModuleHint>
      {steps.length === 0 ? (
        <EmptyState>还没有步骤。可用上方 Add 手动添加。</EmptyState>
      ) : null}
      <DraftStepGrid
        steps={steps}
        onUpdate={onUpdate}
        onDelete={onDelete}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
        onAdd={onAdd}
        onMakeUniqueValue={onMakeUniqueValue}
      />
    </div>
  );
}
