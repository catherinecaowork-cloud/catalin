import type { RecordStep } from "../../types";
import { EmptyState, ModuleHint } from "../ui";
import type { DraftStepPatch } from "./DraftStepCard";
import { DraftStepCard } from "./DraftStepCard";

type Props = {
  steps: RecordStep[];
  onUpdate: (index: number, patch: DraftStepPatch) => void;
  onDelete: (index: number) => void;
  onMakeUniqueValue: (index: number) => void;
};

export function DraftStepList({ steps, onUpdate, onDelete, onMakeUniqueValue }: Props) {
  return (
    <>
      <ModuleHint>步骤在这里滚动查看。连续重复点击已合并。</ModuleHint>
      {steps.length === 0 ? (
        <EmptyState>还没有步骤。</EmptyState>
      ) : (
        steps.map((step, index) => (
          <DraftStepCard
            key={step.id}
            step={step}
            onChange={(patch) => onUpdate(index, patch)}
            onDelete={() => onDelete(index)}
            onMakeUniqueValue={
              step.value !== undefined && step.action !== "goto"
                ? () => onMakeUniqueValue(index)
                : undefined
            }
          />
        ))
      )}
    </>
  );
}
