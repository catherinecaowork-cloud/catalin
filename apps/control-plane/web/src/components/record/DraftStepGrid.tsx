import { KeyRound, Trash2 } from "lucide-react";

import type { RecordStep } from "../../types";
import {
  actionDisplay,
  recordInputEditable,
  resolveRecordInput,
  resolveRecordObject,
} from "../../utils/runStepDisplay";
import { Button, Checkbox, Input, Select } from "../ui";
import { PHASE_OPTIONS } from "./constants";

export type DraftStepPatch = Partial<
  Pick<RecordStep, "label" | "phase" | "mutating" | "value" | "expected">
>;

type Props = {
  steps: RecordStep[];
  onUpdate: (index: number, patch: DraftStepPatch) => void;
  onDelete: (index: number) => void;
  onMakeUniqueValue: (index: number) => void;
};

function templateClass(value: string | undefined) {
  return value && String(value).includes("{{") ? "tpl-var" : "";
}

function inputPatch(step: RecordStep, next: string): DraftStepPatch {
  if (step.value !== undefined) return { value: next };
  if (step.expected !== undefined) return { expected: next };
  return {};
}

export function DraftStepGrid({ steps, onUpdate, onDelete, onMakeUniqueValue }: Props) {
  return (
    <div className="step-grid-wrap draft-step-grid-wrap">
      <table className="step-grid draft-step-grid">
        <thead>
          <tr>
            <th className="col-idx">#</th>
            <th className="col-item">Item</th>
            <th className="col-object">Object</th>
            <th className="col-input">Input</th>
            <th className="col-desc">Description</th>
            <th className="col-phase">分组</th>
            <th className="col-ops">操作</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((step, index) => {
            const objectText = resolveRecordObject(step);
            const inputText = resolveRecordInput(step);
            const inputEditable = recordInputEditable(step);
            const canUnique =
              step.value !== undefined && step.action !== "goto";

            return (
              <tr key={step.id} className="step-grid-row draft-step-grid-row">
                <td className="col-idx">{index + 1}</td>
                <td className="col-item mono" title={step.action}>
                  {actionDisplay(step.action)}
                </td>
                <td className="col-object mono" title={objectText}>
                  {objectText}
                </td>
                <td className="col-input">
                  {inputEditable ? (
                    <Input
                      type="text"
                      className={`cell-input mono ${templateClass(inputText)}`}
                      value={inputText}
                      title="支持 {{unique:key}} / {{now:format}} / {{env:key}}"
                      onChange={(event) =>
                        onUpdate(index, inputPatch(step, event.target.value))
                      }
                    />
                  ) : (
                    <span className="cell-muted">—</span>
                  )}
                </td>
                <td className="col-desc">
                  <Input
                    type="text"
                    className="cell-input"
                    value={step.label ?? step.action}
                    onChange={(event) => onUpdate(index, { label: event.target.value })}
                  />
                </td>
                <td className="col-phase">
                  <Select
                    className="cell-select"
                    value={step.phase ?? ""}
                    onChange={(event) =>
                      onUpdate(index, { phase: event.target.value || undefined })
                    }
                  >
                    {PHASE_OPTIONS.map((option) => (
                      <option key={option.value || "none"} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className="col-ops">
                  <div className="draft-step-ops">
                    <Checkbox
                      className="check compact"
                      label="写"
                      checked={!!step.mutating}
                      onChange={(event) =>
                        onUpdate(index, { mutating: event.target.checked })
                      }
                    />
                    {canUnique ? (
                      <Button
                        variant="inline"
                        className="icon-btn"
                        title="唯一值"
                        onClick={() => onMakeUniqueValue(index)}
                      >
                        <KeyRound size={13} aria-hidden />
                      </Button>
                    ) : null}
                    <Button
                      variant="inline"
                      className="icon-btn danger"
                      title="删除"
                      onClick={() => onDelete(index)}
                    >
                      <Trash2 size={13} aria-hidden />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
