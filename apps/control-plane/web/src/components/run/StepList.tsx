import type { RunStep } from "../../types";
import { EmptyState } from "../ui";
import { StepRow } from "./StepRow";

type Props = {
  steps: RunStep[];
  workersOnline: boolean;
  waitingMessage: string;
  onOpenStepShot: (stepId: string) => void;
};

export function StepList({ steps, workersOnline, waitingMessage, onOpenStepShot }: Props) {
  if (steps.length === 0) {
    return (
      <EmptyState variant={!workersOnline ? "error" : "default"}>
        {waitingMessage}
      </EmptyState>
    );
  }

  return (
    <div className="step-list">
      {steps.map((step) => (
        <StepRow
          key={step.stepId}
          step={step}
          onOpenShot={
            step.screenshot ? () => onOpenStepShot(step.stepId) : undefined
          }
        />
      ))}
    </div>
  );
}
