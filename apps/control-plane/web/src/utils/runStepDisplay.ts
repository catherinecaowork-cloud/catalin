import type { RecordStep, RunStep } from "../types";

const ACTION_LABELS: Record<string, string> = {
  click: "Click",
  fill: "Set Text",
  goto: "Navigate",
  choose: "Choose",
  select: "Select",
  upload: "Upload",
  assert: "Verify",
  pageHealth: "Page Health",
};

export function actionDisplay(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

export function objectFromLabel(label: string): string {
  const matches = [...label.matchAll(/\[([^\]]+)\]/g)];
  if (matches.length) return matches[matches.length - 1][1];
  return "—";
}

export function parseStepDetail(data: Record<string, unknown>): {
  object?: string;
  input?: string;
} {
  const nested = data.data;
  const detail =
    nested && typeof nested === "object" ? (nested as Record<string, unknown>) : {};
  const matched = detail.matched ?? detail.matched_candidate;
  const value = detail.value ?? detail.expected ?? detail.actual ?? detail.wanted;
  return {
    object: matched ? String(matched) : undefined,
    input:
      value !== undefined && value !== null && String(value) !== ""
        ? String(value)
        : undefined,
  };
}

export function resolveStepObject(step: RunStep): string {
  if (step.object) return step.object;
  return objectFromLabel(step.label);
}

export function resolveStepInput(step: RunStep): string {
  if (step.input) return step.input;
  return "—";
}

export function resolveRecordObject(step: RecordStep): string {
  const target = step.target as
    | { candidates?: Array<{ kind?: string; value?: string }> }
    | undefined;
  const candidates = target?.candidates;
  if (candidates?.length) {
    const primary = candidates.find((item) => item.value) ?? candidates[0];
    if (primary?.value) return String(primary.value);
  }
  const label = step.label ?? "";
  const cn = label.match(/「([^」]+)」/);
  if (cn) return cn[1];
  const bracket = objectFromLabel(label);
  return bracket !== "—" ? bracket : "—";
}

export function resolveRecordInput(step: RecordStep): string {
  if (step.value !== undefined) return String(step.value);
  if (step.expected !== undefined) return String(step.expected);
  return "";
}

export function recordInputEditable(step: RecordStep): boolean {
  return step.value !== undefined || step.expected !== undefined;
}
