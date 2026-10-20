import type { RunStep } from "../../types";
import {
  actionDisplay,
  resolveStepInput,
  resolveStepObject,
} from "../../utils/runStepDisplay";
import { cn, EmptyState } from "../ui";

type Props = {
  steps: RunStep[];
  variant?: "full" | "compact";
  emptyMessage?: string;
  onOpenStepShot?: (stepId: string) => void;
};

/** 失败分类的中文名。三类混成一句「偶发失败」，运维就不知道该改脚本还是看环境。 */
const FAILURE_LABELS: Record<string, string> = {
  not_found: "没找到",
  not_actionable: "找到但点不到",
  no_effect: "点了没生效",
};

function failureLabel(failure?: string): string | undefined {
  return failure ? (FAILURE_LABELS[failure] ?? failure) : undefined;
}

export function RunStepGrid({
  steps,
  variant = "full",
  emptyMessage = "还没有步骤。",
  onOpenStepShot,
}: Props) {
  if (!steps.length) {
    return <EmptyState>{emptyMessage}</EmptyState>;
  }

  const compact = variant === "compact";

  return (
    <div className={cn("step-grid-wrap", compact && "compact")}>
      <table className="step-grid">
        <thead>
          <tr>
            {!compact ? <th className="col-idx">#</th> : null}
            <th className="col-status" aria-label="状态" />
            {compact ? (
              <>
                <th className="col-desc">描述</th>
                <th className="col-item">动作</th>
              </>
            ) : (
              <>
                <th className="col-item">Item</th>
                <th className="col-object">Object</th>
                <th className="col-input">Input</th>
                <th className="col-desc">Description</th>
              </>
            )}
            <th className="col-ms">Duration</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((step, index) => {
            const clickable = !!step.screenshot && !!onOpenStepShot;
            const objectText = resolveStepObject(step);
            const inputText = resolveStepInput(step);

            return (
              <tr
                key={step.stepId}
                className={cn(
                  "step-grid-row",
                  step.status,
                  clickable && "has-shot",
                )}
                onClick={clickable ? () => onOpenStepShot(step.stepId) : undefined}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && clickable) onOpenStepShot(step.stepId);
                }}
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
              >
                {!compact ? <td className="col-idx">{index + 1}</td> : null}
                <td className="col-status">
                  <span className="dot" aria-hidden />
                </td>
                {compact ? (
                  <>
                    <td className="col-desc">
                      <div className="cell-main">{step.label}</div>
                      {step.message ? <div className="msg">{step.message}</div> : null}
                      {failureLabel(step.failure) ? (
                        <div className="failure">{failureLabel(step.failure)}</div>
                      ) : null}
                      {step.drift ? <div className="drift">{step.drift}</div> : null}
                    </td>
                    <td className="col-item mono">{step.action}</td>
                  </>
                ) : (
                  <>
                    <td className="col-item mono" title={step.action}>
                      {actionDisplay(step.action)}
                    </td>
                    <td className="col-object mono" title={objectText}>
                      {objectText}
                    </td>
                    <td className="col-input mono" title={inputText}>
                      {inputText}
                    </td>
                    <td className="col-desc">
                      <div className="cell-main">{step.label}</div>
                      {step.message ? <div className="msg">{step.message}</div> : null}
                      {failureLabel(step.failure) ? (
                        <div className="failure">{failureLabel(step.failure)}</div>
                      ) : null}
                      {step.drift ? <div className="drift">{step.drift}</div> : null}
                    </td>
                  </>
                )}
                <td className="col-ms">
                  {step.elapsed !== undefined ? `${step.elapsed} ms` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
