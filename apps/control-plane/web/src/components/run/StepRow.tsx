import type { RunStep } from "../../types";
import { cn } from "../ui";

type Props = {
  step: RunStep;
  onOpenShot?: () => void;
};

export function StepRow({ step, onOpenShot }: Props) {
  const clickable = !!step.screenshot && !!onOpenShot;

  return (
    <div
      className={cn("step", step.status, clickable && "has-shot")}
      onClick={clickable ? onOpenShot : undefined}
      onKeyDown={(event) => event.key === "Enter" && clickable && onOpenShot?.()}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
    >
      <div className="dot" />
      <div className="step-body">
        <div>
          {step.label}
          <span className="action">{step.action}</span>
        </div>
        {step.message ? <div className="msg">{step.message}</div> : null}
        {step.drift ? <div className="drift">{step.drift}</div> : null}
      </div>
      <div className="ms">{step.elapsed !== undefined ? `${step.elapsed} ms` : ""}</div>
    </div>
  );
}
