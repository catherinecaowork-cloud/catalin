import type { RecordLiveAction } from "../types";
import { actionDisplay, pickBestRecordCandidate } from "./runStepDisplay";

export function liveActionItem(action: RecordLiveAction, sequence: number): string {
  return `${sequence} - ${actionDisplay(action.type)}`;
}

export function liveActionObject(action: RecordLiveAction): string {
  const picked = pickBestRecordCandidate({ candidates: action.candidates });
  if (picked) return picked;
  if (action.label?.trim()) return action.label.trim();
  if (action.text?.trim() && !/^(请选择|请输入|请填写)/.test(action.text.trim())) {
    return action.text.trim();
  }
  return "—";
}

export function liveActionInput(action: RecordLiveAction): string {
  if (action.type === "fill" || action.type === "choose" || action.type === "select") {
    return action.value?.trim() || "—";
  }
  if (action.type === "upload") return action.value?.trim() || action.text?.trim() || "—";
  if (action.type === "press") return action.value?.trim() || action.text?.trim() || "Enter";
  if (action.type === "click" && action.text?.trim()) return action.text.trim();
  return "—";
}

export function liveActionDescription(action: RecordLiveAction): string {
  const parts = [action.scope, action.dialog].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}
