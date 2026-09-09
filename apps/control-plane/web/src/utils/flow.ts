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

export function flowSetupName(flow: Flow, flows: Flow[]): string {
  if (!flow.setup_flow_id) return "";
  return flows.find((item) => item.id === flow.setup_flow_id)?.name ?? "";
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
