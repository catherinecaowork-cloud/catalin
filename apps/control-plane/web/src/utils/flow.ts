import type { Flow, Site } from "../types";

export function flowStatusText(status: string): string {
  const map: Record<string, string> = {
    draft: "草稿",
    reviewed: "用例",
    golden: "黄金基线",
    active: "回归中",
  };
  return map[status] ?? status;
}

export function isConfirmedFlow(flow: Flow | undefined): boolean {
  return !!flow && ["reviewed", "golden", "active"].includes(flow.status);
}

export function flowSetupIds(flow: Flow): string[] {
  if (flow.setup_flow_ids?.length) return flow.setup_flow_ids;
  return flow.setup_flow_id ? [flow.setup_flow_id] : [];
}

export function flowSetupNames(flow: Flow, flows: Flow[]): string[] {
  return flowSetupIds(flow)
    .map((id) => flows.find((item) => item.id === id)?.name ?? "")
    .filter(Boolean);
}

export function flowSetupName(flow: Flow, flows: Flow[]): string {
  const names = flowSetupNames(flow, flows);
  return names.join(" → ");
}

export function flowListSub(flow: Flow, flows: Flow[]): string {
  const parts = [flowStatusText(flow.status)];
  if (flow.imported_from) parts.push(`导入·${flow.imported_from}`);
  const setup = flowSetupName(flow, flows);
  if (setup) parts.push(`前置·${setup}`);
  return parts.join(" · ");
}

export function statusText(status: string): string {
  const map: Record<string, string> = {
    queued: "排队",
    leased: "已领取",
    running: "运行中",
    passed: "通过",
    failed: "失败",
    error: "异常",
    skipped: "跳过",
  };
  return map[status] ?? status;
}

export function otherSites(sites: Site[], selectedSiteId: string | null): Site[] {
  return sites.filter((site) => site.id !== selectedSiteId);
}
