import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "../api/client";
import type { Batch, Flow, Site, Suite } from "../types";
import { isConfirmedFlow } from "../utils/flow";

type RunContextValue = {
  siteId: string | null;
  sites: Site[];
  flows: Flow[];
  suites: Suite[];
  selectedFlowId: string | null;
  setSelectedFlowId: (id: string | null) => void;
  selectedPicks: Set<string>;
  togglePick: (flowId: string, checked: boolean) => void;
  selectedSuiteId: string | null;
  selectSuite: (suiteId: string) => void;
  clearSuiteSelection: () => void;
  headed: boolean;
  setHeaded: (value: boolean) => void;
  dryRun: boolean;
  setDryRun: (value: boolean) => void;
  loading: boolean;
  refresh: () => Promise<void>;
  saveSuite: (name: string) => Promise<void>;
  deleteSuite: (suiteId: string) => Promise<void>;
  updateSetup: (flowId: string, setupFlowId: string | null) => Promise<void>;
  promoteFlow: (flow: Flow) => Promise<void>;
  deleteFlow: (flow: Flow) => Promise<void>;
  importFlows: (flowIds: string[]) => Promise<{ imported: string[]; skipped: string[] }>;
  startSingleRun: () => Promise<{ runId: string; title: string }>;
  startPickedRuns: () => Promise<{ batch: Batch; title: string }>;
  pickedFlowIds: () => string[];
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

const RunContext = createContext<RunContextValue | null>(null);

export function useRunContext() {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRunContext 必须在 RunProvider 内使用");
  return ctx;
}

type Props = {
  siteId: string | null;
  sites: Site[];
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  children: ReactNode;
};

export function RunProvider({ siteId, sites, onLog, children }: Props) {
  const [flows, setFlows] = useState<Flow[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [selectedFlowId, setSelectedFlowId] = useState<string | null>(null);
  const [selectedPicks, setSelectedPicks] = useState<Set<string>>(new Set());
  const [selectedSuiteId, setSelectedSuiteId] = useState<string | null>(null);
  const [headed, setHeaded] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [loading, setLoading] = useState(false);

  const prunePicks = useCallback((rows: Flow[], picks: Set<string>) => {
    return new Set(
      [...picks].filter((id) => isConfirmedFlow(rows.find((flow) => flow.id === id))),
    );
  }, []);

  const refresh = useCallback(async () => {
    if (!siteId) {
      setFlows([]);
      setSuites([]);
      setSelectedFlowId(null);
      setSelectedPicks(new Set());
      setSelectedSuiteId(null);
      return;
    }
    setLoading(true);
    try {
      const [flowRows, suiteRows] = await Promise.all([
        api<Flow[]>(`/api/v1/flows?site_id=${encodeURIComponent(siteId)}`),
        api<Suite[]>(`/api/v1/suites?site_id=${encodeURIComponent(siteId)}`),
      ]);
      setFlows(flowRows);
      setSuites(suiteRows);
      setSelectedFlowId((current) =>
        current && flowRows.some((flow) => flow.id === current) ? current : null,
      );
      setSelectedPicks((current) => prunePicks(flowRows, current));
    } catch (err) {
      onLog(`加载流程失败：${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [siteId, onLog, prunePicks]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pickedFlowIds = useCallback(() => {
    const suite = suites.find((item) => item.id === selectedSuiteId);
    if (suite) {
      return suite.flow_ids.filter((id) => selectedPicks.has(id));
    }
    return flows
      .filter((flow) => selectedPicks.has(flow.id) && isConfirmedFlow(flow))
      .map((flow) => flow.id);
  }, [flows, suites, selectedPicks, selectedSuiteId]);

  const togglePick = useCallback(
    (flowId: string, checked: boolean) => {
      setSelectedPicks((prev) => {
        const next = new Set(prev);
        if (checked) next.add(flowId);
        else next.delete(flowId);
        return next;
      });
      setSelectedSuiteId(null);
    },
    [],
  );

  const selectSuite = useCallback(
    (suiteId: string) => {
      const suite = suites.find((item) => item.id === suiteId);
      if (!suite) return;
      setSelectedSuiteId(suiteId);
      setSelectedPicks(new Set(suite.flow_ids ?? []));
      onLog(`已勾选套件「${suite.name}」`);
    },
    [suites, onLog],
  );

  const saveSuite = useCallback(
    async (name: string) => {
      const ids = pickedFlowIds();
      if (!siteId || !ids.length) throw new Error("先勾选已确认用例");
      const suite = await api<Suite>("/api/v1/suites", {
        method: "POST",
        body: JSON.stringify({ site_id: siteId, name, flow_ids: ids }),
      });
      setSelectedSuiteId(suite.id);
      onLog(`已保存套件「${suite.name}」`);
      await refresh();
    },
    [siteId, pickedFlowIds, onLog, refresh],
  );

  const deleteSuite = useCallback(
    async (suiteId: string) => {
      await api(`/api/v1/suites/${suiteId}`, { method: "DELETE" });
      if (selectedSuiteId === suiteId) setSelectedSuiteId(null);
      onLog("已删除套件");
      await refresh();
    },
    [selectedSuiteId, onLog, refresh],
  );

  const updateSetup = useCallback(
    async (flowId: string, setupFlowId: string | null) => {
      const updated = await api<Flow>(`/api/v1/flows/${flowId}/setup`, {
        method: "POST",
        body: JSON.stringify({ setup_flow_id: setupFlowId }),
      });
      setFlows((prev) => prev.map((flow) => (flow.id === updated.id ? updated : flow)));
      const flow = flows.find((item) => item.id === flowId);
      const setup = setupFlowId
        ? flows.find((item) => item.id === setupFlowId)
        : null;
      onLog(
        setup && flow
          ? `「${flow.name}」前置为「${setup.name}」`
          : flow
            ? `「${flow.name}」已去掉前置`
            : "前置已更新",
      );
      await refresh();
    },
    [flows, onLog, refresh],
  );

  const promoteFlow = useCallback(
    async (flow: Flow) => {
      const toDraft = flow.status !== "draft";
      const nextStatus = toDraft ? "draft" : "reviewed";
      await api(`/api/v1/flows/${flow.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: nextStatus }),
      });
      setSelectedFlowId(flow.id);
      onLog(toDraft ? `已将「${flow.name}」退回草稿` : `已确认「${flow.name}」为用例`);
      await refresh();
    },
    [onLog, refresh],
  );

  const deleteFlow = useCallback(
    async (flow: Flow) => {
      await api(`/api/v1/flows/${flow.id}`, { method: "DELETE" });
      if (selectedFlowId === flow.id) setSelectedFlowId(null);
      onLog(`已删除流程 ${flow.name}`);
      await refresh();
    },
    [selectedFlowId, onLog, refresh],
  );

  const importFlows = useCallback(
    async (flowIds: string[]) => {
      if (!siteId) throw new Error("未选择站点");
      const result = await api<{ imported: string[]; skipped: string[] }>(
        `/api/v1/sites/${siteId}/flows/import`,
        { method: "POST", body: JSON.stringify({ flow_ids: flowIds }) },
      );
      if (result.imported?.length) onLog(`已导入 ${result.imported.join("、")}`);
      (result.skipped ?? []).forEach((msg) => onLog(msg, "warn"));
      await refresh();
      return result;
    },
    [siteId, onLog, refresh],
  );

  const startSingleRun = useCallback(async () => {
    if (!selectedFlowId) throw new Error("先在列表里点选一条流程");
    const flow = flows.find((item) => item.id === selectedFlowId);
    const setup = flow?.setup_flow_id
      ? flows.find((item) => item.id === flow.setup_flow_id)
      : null;
    const run = await api<{ id: string }>("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify({
        flow_id: selectedFlowId,
        site_id: siteId ?? undefined,
        headless: !headed,
        dry_run: dryRun,
      }),
    });
    onLog(
      setup && flow
        ? `已入队「${setup.name} → ${flow.name}」（同一次登录）`
        : `已入队 ${run.id.slice(0, 8)}`,
    );
    return { runId: run.id, title: `运行 ${run.id.slice(0, 8)}` };
  }, [selectedFlowId, flows, siteId, headed, dryRun, onLog]);

  const startPickedRuns = useCallback(async () => {
    const ids = pickedFlowIds();
    if (!ids.length) throw new Error("先勾选已确认用例");
    const suite = suites.find((item) => item.id === selectedSuiteId);
    const batch = await api<Batch>("/api/v1/batches", {
      method: "POST",
      body: JSON.stringify({
        site_id: siteId,
        flow_ids: ids,
        suite_id:
          suite && JSON.stringify(suite.flow_ids) === JSON.stringify(ids)
            ? suite.id
            : null,
        headless: !headed,
        dry_run: dryRun,
      }),
    });
    const total = batch.flow_ids?.length ?? 1;
    const n = (batch.current_index ?? 0) + 1;
    const title = total <= 1 ? batch.name : `${batch.name} ${n}/${total}`;
    onLog(total <= 1 ? `${batch.name} 已入队（同一次登录）` : title);
    if (!batch.current_run_id) throw new Error("批次未生成运行");
    return { batch, title };
  }, [pickedFlowIds, suites, selectedSuiteId, siteId, headed, dryRun, onLog]);

  const value = useMemo<RunContextValue>(
    () => ({
      siteId,
      sites,
      flows,
      suites,
      selectedFlowId,
      setSelectedFlowId,
      selectedPicks,
      togglePick,
      selectedSuiteId,
      selectSuite,
      clearSuiteSelection: () => setSelectedSuiteId(null),
      headed,
      setHeaded,
      dryRun,
      setDryRun,
      loading,
      refresh,
      saveSuite,
      deleteSuite,
      updateSetup,
      promoteFlow,
      deleteFlow,
      importFlows,
      startSingleRun,
      startPickedRuns,
      pickedFlowIds,
      onLog,
    }),
    [
      siteId,
      sites,
      flows,
      suites,
      selectedFlowId,
      selectedPicks,
      togglePick,
      selectedSuiteId,
      selectSuite,
      headed,
      dryRun,
      loading,
      refresh,
      saveSuite,
      deleteSuite,
      updateSetup,
      promoteFlow,
      deleteFlow,
      importFlows,
      startSingleRun,
      startPickedRuns,
      pickedFlowIds,
      onLog,
    ],
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}
