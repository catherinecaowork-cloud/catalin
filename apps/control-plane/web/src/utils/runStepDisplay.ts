import type { RecordStep, RunStep } from "../types";

const ACTION_LABELS: Record<string, string> = {
  click: "Click",
  fill: "Set Text",
  goto: "Navigate",
  choose: "Choose",
  press: "Press Key",
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

type RecordCandidate = { kind?: string; value?: string; name?: string | null };

const NOISE_OBJECT_TEXT = new Set([
  "请选择",
  "请输入",
  "请填写",
  "下拉",
  "搜索",
  "添加",
  "元素",
  "输入框",
  "—",
  "-",
  "–",
  "一",
]);

function isNoiseObjectText(value: string): boolean {
  const text = value.trim();
  if (!text) return true;
  if (NOISE_OBJECT_TEXT.has(text)) return true;
  return /^(请输入|请选择|请填写)/.test(text);
}

function recordCandidateRank(candidate: RecordCandidate): number {
  switch (candidate.kind) {
    case "field":
    case "matrix":
      return 0;
    case "testid":
      return 1;
    case "label":
      return 2;
    case "css":
      return 3;
    case "role":
      return String(candidate.name ?? "").trim() ? 4 : 8;
    case "placeholder":
      return 5;
    case "text":
      return 6;
    default:
      return 7;
  }
}

function formatRecordCandidate(candidate: RecordCandidate): string {
  const value = String(candidate.value ?? "").trim();
  const name = String(candidate.name ?? "").trim();
  if (candidate.kind === "role" && name) {
    return `${value}_${name}`.replace(/\s+/g, "_");
  }
  return value;
}

export function pickBestRecordCandidate(
  target?: {
    candidates?: RecordCandidate[];
    trigger_css?: string;
  } | null,
): string | null {
  if (!target) return null;
  const triggerCss = String(target.trigger_css ?? "").trim();
  if (triggerCss) return triggerCss;

  const ranked = [...(target.candidates ?? [])]
    .filter((item) => item.value && !isNoiseObjectText(String(item.value)))
    .sort(
      (left, right) =>
        recordCandidateRank(left) - recordCandidateRank(right) ||
        String(left.value).length - String(right.value).length,
    );

  if (ranked.length) return formatRecordCandidate(ranked[0]);
  return null;
}

export function resolveRecordObject(step: RecordStep): string {
  const target = step.target as
    | { candidates?: RecordCandidate[]; trigger_css?: string }
    | undefined;
  const picked = pickBestRecordCandidate(target);
  if (picked) return picked;

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
