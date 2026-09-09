import type { ModuleKind } from "../types";
import { MODULES } from "../types";

export function newTabId(kind: ModuleKind) {
  return `mod-${kind}-${Date.now()}`;
}

export function runTabId(runId: string) {
  return `run-${runId}`;
}

export function recTabId(runId: string) {
  return `rec-${runId}`;
}

export function parseRunTabId(tabId: string) {
  return tabId.startsWith("run-") ? tabId.slice(4) : null;
}

export function parseRecTabId(tabId: string) {
  return tabId.startsWith("rec-") ? tabId.slice(4) : null;
}

export function isModuleTab(tabId: string) {
  return tabId.startsWith("mod-");
}

export function openTabTitle(kind: ModuleKind, custom?: string) {
  return custom ?? MODULES[kind].title;
}
