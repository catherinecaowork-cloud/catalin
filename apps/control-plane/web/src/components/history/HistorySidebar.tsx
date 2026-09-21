import { useMemo, useState } from "react";

import { useHistoryContext } from "../../context/HistoryContext";
import { ExplorerTree, type ExplorerNode } from "../patterns/ExplorerTree";
import { Button, EmptyState, ModuleHint } from "../ui";

type Props = {
  onOpenRun: (runId: string, title: string) => void;
};

export function HistorySidebar({ onOpenRun }: Props) {
  const history = useHistoryContext();
  const [filter, setFilter] = useState("");
  const picked = history.selected.size;

  const nodes = useMemo((): ExplorerNode[] => {
    const runNodes: ExplorerNode[] = history.runs.map((run) => {
      const busy = history.isBusy(run);
      const time = new Date(run.created_at).toLocaleString("zh-CN", { hour12: false });
      const dur = run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : "";
      return {
        id: run.id,
        kind: "run" as const,
        label: `${history.kindText(run.kind)} · ${history.statusText(run.status)}`,
        sub: `${time} ${dur}`.trim(),
        markColor: "var(--c-history)",
        selected: history.selected.has(run.id),
        disabled: busy,
        onSelect: (event) => {
          const additive = Boolean(event?.ctrlKey || event?.metaKey);
          const range = Boolean(event?.shiftKey);
          history.selectRun(run.id, { additive, range });
          if (!additive && !range) {
            onOpenRun(run.id, `运行 ${run.id.slice(0, 8)}`);
          }
        },
      };
    });

    if (!runNodes.length) return [];
    return [
      {
        id: "folder-runs",
        kind: "folder",
        label: "运行记录",
        sub: picked ? `${runNodes.length} · 已选 ${picked}` : String(runNodes.length),
        children: runNodes,
      },
    ];
  }, [history, onOpenRun, picked]);

  return (
    <>
      <ModuleHint>
        单击打开；Ctrl 单击加选，Shift 单击选区间，Ctrl+A 全选。进行中的记录不能选。
      </ModuleHint>
      {history.loading ? (
        <EmptyState>加载中…</EmptyState>
      ) : history.runs.length === 0 ? (
        <EmptyState>当前站点还没有运行记录。</EmptyState>
      ) : (
        <ExplorerTree
          nodes={nodes}
          filter={filter}
          onFilterChange={setFilter}
          filterPlaceholder="搜索运行记录…"
          emptyMessage="没有匹配的运行记录"
          onSelectAll={history.selectAll}
        />
      )}
    </>
  );
}

export function HistorySidebarFoot({ onRefreshWorkers }: { onRefreshWorkers: () => void }) {
  const history = useHistoryContext();
  const picked = history.selected.size;

  return (
    <div className="run-foot">
      <Button
        variant="ghost"
        onClick={() => {
          onRefreshWorkers();
          void history.refresh();
        }}
      >
        刷新列表
      </Button>
      <Button
        variant="danger"
        style={{ marginTop: 8 }}
        disabled={picked === 0}
        onClick={() => void history.deleteSelected()}
      >
        删除所选
      </Button>
    </div>
  );
}
