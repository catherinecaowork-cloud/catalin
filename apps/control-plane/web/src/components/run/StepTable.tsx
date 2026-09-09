import type { RunStep } from "../../types";
import { RunStepGrid } from "./RunStepGrid";

type Props = {
  steps: RunStep[];
};

export function StepTable({ steps }: Props) {
  return (
    <RunStepGrid
      steps={steps}
      variant="compact"
      emptyMessage="运行中的步骤会显示在这里。"
    />
  );
}
