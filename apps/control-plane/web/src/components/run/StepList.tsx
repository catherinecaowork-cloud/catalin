import type { RunStep } from "../../types";
import { EmptyState } from "../ui";
import { RunStepGrid } from "./RunStepGrid";

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
    <RunStepGrid
      steps={steps}
      variant="full"
      onOpenStepShot={onOpenStepShot}
    />
  );
}
