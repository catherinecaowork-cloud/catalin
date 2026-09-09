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
import type { RunRecord } from "../types";
import { kindText } from "../utils/kind";
import { statusText } from "../utils/flow";

type HistoryContextValue = {
  runs: RunRecord[];
  selected: Set<string>;
  loading: boolean;
  refresh: () => Promise<void>;
  notifyRunFinished: () => void;
  togglePick: (runId: string, checked: boolean) => void;
  toggleAll: (checked: boolean) => void;
  deleteSelected: () => Promise<void>;
  isBusy: (run: RunRecord) => boolean;
  kindText: (kind: string) => string;
  statusText: (status: string) => string;
};

const HistoryContext = createContext<HistoryContextValue | null>(null);

export function useHistoryContext() {
  const ctx = useContext(HistoryContext);
  if (!ctx) throw new Error("useHistoryContext 必须在 HistoryProvider 内使用");
  return ctx;
}

export function HistoryProvider({
  siteId,
  onLog,
  children,
}: {
  siteId: string | null;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  children: ReactNode;
}) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);

  const isBusy = useCallback(
    (run: RunRecord) => ["queued", "leased", "running"].includes(run.status),
    [],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api<RunRecord[]>("/api/v1/runs?limit=100");
      setRuns(rows.filter((run) => !siteId || run.site_id === siteId));
      setSelected(new Set());
    } catch (err) {
      onLog(`加载历史失败：${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [siteId, onLog]);

  const notifyRunFinished = useCallback(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const togglePick = useCallback((runId: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(runId);
      else next.delete(runId);
      return next;
    });
  }, []);

  const toggleAll = useCallback(
    (checked: boolean) => {
      if (!checked) {
        setSelected(new Set());
        return;
      }
      const ids = runs.filter((run) => !isBusy(run)).map((run) => run.id);
      setSelected(new Set(ids));
    },
    [runs, isBusy],
  );

  const deleteSelected = useCallback(async () => {
    const ids = [...selected];
    if (!ids.length) return;
    if (!window.confirm(`删除选中的 ${ids.length} 条记录？截图和事件会一起清掉，不可恢复。`)) {
      return;
    }
    try {
      const result = await api<{ deleted?: string[]; skipped?: string[] }>(
        "/api/v1/history/purge",
        { method: "POST", body: JSON.stringify({ ids }) },
      );
      const gone = result.deleted?.length ?? 0;
      const skip = result.skipped?.length ?? 0;
      onLog(`已删除 ${gone} 条` + (skip ? `，跳过 ${skip} 条` : ""));
      await refresh();
    } catch (err) {
      onLog(`删除失败：${err instanceof Error ? err.message : String(err)}`, "error");
    }
  }, [selected, onLog, refresh]);

  const value = useMemo<HistoryContextValue>(
    () => ({
      runs,
      selected,
      loading,
      refresh,
      notifyRunFinished,
      togglePick,
      toggleAll,
      deleteSelected,
      isBusy,
      kindText,
      statusText,
    }),
    [
      runs,
      selected,
      loading,
      refresh,
      notifyRunFinished,
      togglePick,
      toggleAll,
      deleteSelected,
      isBusy,
    ],
  );

  return <HistoryContext.Provider value={value}>{children}</HistoryContext.Provider>;
}
