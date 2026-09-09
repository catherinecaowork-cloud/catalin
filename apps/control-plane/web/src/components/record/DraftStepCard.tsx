import type { RecordStep } from "../../types";
import { Button, Checkbox, Input, Select } from "../ui";
import { PHASE_OPTIONS } from "./constants";

export type DraftStepPatch = Partial<
  Pick<RecordStep, "label" | "phase" | "mutating" | "value" | "expected">
>;

type Props = {
  step: RecordStep;
  onChange: (patch: DraftStepPatch) => void;
  onDelete: () => void;
  onMakeUniqueValue?: () => void;
};

function templateClass(value: string | undefined) {
  return value && String(value).includes("{{") ? "tpl-var" : "";
}

export function DraftStepCard({ step, onChange, onDelete, onMakeUniqueValue }: Props) {
  return (
    <div className="draft-step">
      <Input
        type="text"
        value={step.label ?? step.action}
        onChange={(event) => onChange({ label: event.target.value })}
      />
      <div className="meta">
        <span>{step.action}</span>
        <Select
          value={step.phase ?? ""}
          onChange={(event) => onChange({ phase: event.target.value || undefined })}
        >
          {PHASE_OPTIONS.map((option) => (
            <option key={option.value || "none"} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Checkbox
          label="写操作"
          checked={!!step.mutating}
          onChange={(event) => onChange({ mutating: event.target.checked })}
        />
        {step.value !== undefined && step.action !== "goto" && onMakeUniqueValue ? (
          <Button variant="inline" onClick={onMakeUniqueValue}>
            唯一值
          </Button>
        ) : null}
        <Button variant="inline" onClick={onDelete}>
          删除
        </Button>
      </div>
      {step.value !== undefined ? (
        <Input
          type="text"
          value={String(step.value)}
          title="支持 {{unique:key}} / {{now:format}} / {{env:key}}"
          className={templateClass(step.value)}
          onChange={(event) => onChange({ value: event.target.value })}
        />
      ) : null}
      {step.expected !== undefined ? (
        <Input
          type="text"
          value={String(step.expected)}
          className={templateClass(step.expected)}
          onChange={(event) => onChange({ expected: event.target.value })}
        />
      ) : null}
    </div>
  );
}
