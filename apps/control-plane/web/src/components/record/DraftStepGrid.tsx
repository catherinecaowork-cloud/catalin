import { ArrowDown, ArrowUp, KeyRound, PenLine, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { RecordStep } from "../../types";
import {
  actionDisplay,
  recordInputEditable,
  resolveRecordInput,
  resolveRecordObject,
} from "../../utils/runStepDisplay";
import { Button, Input, Select } from "../ui";
import { PHASE_OPTIONS } from "./constants";

export type DraftStepPatch = Partial<
  Pick<RecordStep, "label" | "phase" | "mutating" | "value" | "expected">
>;

type Props = {
  steps: RecordStep[];
  onUpdate: (index: number, patch: DraftStepPatch) => void;
  onDelete: (index: number) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onAdd: (action: string, afterIndex?: number) => void;
  onMakeUniqueValue: (index: number) => void;
};

const ADD_ACTIONS = [
  { value: "click", label: "Click" },
  { value: "fill", label: "Set Text" },
  { value: "choose", label: "Choose" },
  { value: "assert", label: "Verify" },
] as const;

function templateClass(value: string | undefined) {
  return value && String(value).includes("{{") ? "tpl-var" : "";
}

function inputPatch(step: RecordStep, next: string): DraftStepPatch {
  if (step.value !== undefined) return { value: next };
  if (step.expected !== undefined) return { expected: next };
  return {};
}

export function DraftStepGrid({
  steps,
  onUpdate,
  onDelete,
  onMoveUp,
  onMoveDown,
  onAdd,
  onMakeUniqueValue,
}: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(
    steps.length ? 0 : null,
  );
  const [addAction, setAddAction] = useState<string>("click");

  useEffect(() => {
    setSelectedIndex((current) => {
      if (!steps.length) return null;
      if (current === null) return 0;
      return Math.min(current, steps.length - 1);
    });
  }, [steps.length]);

  const selectedStep = useMemo(
    () => (selectedIndex === null ? null : steps[selectedIndex] ?? null),
    [selectedIndex, steps],
  );

  const canUnique =
    selectedStep !== null &&
    selectedStep.value !== undefined &&
    selectedStep.action !== "goto";

  const insertAfter = selectedIndex ?? undefined;

  return (
    <div className="step-grid-wrap draft-step-grid-wrap">
      <div className="draft-step-console" role="toolbar" aria-label="步骤编辑">
        <div className="draft-step-console-group">
          <Select
            className="draft-step-add-select"
            value={addAction}
            aria-label="新增步骤类型"
            onChange={(event) => setAddAction(event.target.value)}
          >
            {ADD_ACTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Button
            variant="ghost"
            className="draft-step-console-btn"
            title="在选中步骤后新增"
            onClick={() => onAdd(addAction, insertAfter)}
          >
            <Plus size={13} aria-hidden />
            Add
          </Button>
        </div>
        <span className="draft-step-console-sep" aria-hidden="true" />
        <div className="draft-step-console-group">
          <Button
            variant="ghost"
            className="draft-step-console-btn danger"
            title="删除选中步骤"
            disabled={selectedIndex === null}
            onClick={() => {
              if (selectedIndex === null) return;
              onDelete(selectedIndex);
            }}
          >
            <Trash2 size={13} aria-hidden />
            Remove
          </Button>
          <Button
            variant="ghost"
            className="draft-step-console-btn"
            title="上移"
            disabled={selectedIndex === null || selectedIndex <= 0}
            onClick={() => {
              if (selectedIndex === null) return;
              onMoveUp(selectedIndex);
              setSelectedIndex(selectedIndex - 1);
            }}
          >
            <ArrowUp size={13} aria-hidden />
          </Button>
          <Button
            variant="ghost"
            className="draft-step-console-btn"
            title="下移"
            disabled={selectedIndex === null || selectedIndex >= steps.length - 1}
            onClick={() => {
              if (selectedIndex === null) return;
              onMoveDown(selectedIndex);
              setSelectedIndex(selectedIndex + 1);
            }}
          >
            <ArrowDown size={13} aria-hidden />
          </Button>
        </div>
        <span className="draft-step-console-sep" aria-hidden="true" />
        <div className="draft-step-console-group">
          <Button
            variant="ghost"
            className={`draft-step-console-btn ${selectedStep?.mutating ? "active" : ""}`}
            title="标记为写操作（会改被测数据）"
            disabled={selectedIndex === null}
            onClick={() => {
              if (selectedIndex === null) return;
              onUpdate(selectedIndex, { mutating: !selectedStep?.mutating });
            }}
          >
            <PenLine size={13} aria-hidden />
            写
          </Button>
          <Button
            variant="ghost"
            className="draft-step-console-btn"
            title="Input 改为唯一值模板"
            disabled={!canUnique || selectedIndex === null}
            onClick={() => {
              if (selectedIndex === null) return;
              onMakeUniqueValue(selectedIndex);
            }}
          >
            <KeyRound size={13} aria-hidden />
          </Button>
        </div>
      </div>

      <table className="step-grid draft-step-grid">
        <thead>
          <tr>
            <th className="col-idx">#</th>
            <th className="col-item">Item</th>
            <th className="col-object">Object</th>
            <th className="col-input">Input</th>
            <th className="col-desc">Description</th>
            <th className="col-phase">分组</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((step, index) => {
            const objectText = resolveRecordObject(step);
            const inputText = resolveRecordInput(step);
            const inputEditable = recordInputEditable(step);
            const selected = selectedIndex === index;

            return (
              <tr
                key={step.id}
                className={`step-grid-row draft-step-grid-row ${selected ? "selected" : ""}`}
                onClick={() => setSelectedIndex(index)}
              >
                <td className="col-idx">{index + 1}</td>
                <td className="col-item mono" title={step.action}>
                  {index + 1} - {actionDisplay(step.action)}
                </td>
                <td className="col-object mono" title={objectText}>
                  {objectText}
                </td>
                <td className="col-input" onClick={(event) => event.stopPropagation()}>
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
                <td className="col-desc" onClick={(event) => event.stopPropagation()}>
                  <Input
                    type="text"
                    className="cell-input"
                    value={step.label ?? step.action}
                    onChange={(event) => onUpdate(index, { label: event.target.value })}
                  />
                </td>
                <td className="col-phase" onClick={(event) => event.stopPropagation()}>
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
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
