import { FolderInput, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { useHistoryContext } from "../../context/HistoryContext";
import { useRunContext } from "../../context/RunContext";
import type { Flow } from "../../types";
import { flowListSub, isConfirmedFlow } from "../../utils/flow";
import { ConfirmModal } from "../patterns/ConfirmModal";
import { FlowExplorerContextMenu } from "../patterns/FlowExplorerContextMenu";
import { FlowSetupModal } from "../patterns/FlowSetupModal";
import { ExplorerTree, type ExplorerNode } from "../patterns/ExplorerTree";
import { useConfirmDialog } from "../../hooks/useConfirmDialog";
import { Sidebar, SidebarBody, SidebarFoot } from "../layout/Sidebar";
import { Checkbox, EmptyState, Muted } from "../ui";
import { DeleteFlowModal } from "../run/DeleteFlowModal";
import { ImportFlowsModal } from "../run/ImportFlowsModal";
import { RunSidebarFootActions } from "../run/RunSidebar";

type Props = {
  siteName: string | null;
  onOpenRun: (runId: string, title: string, headed: boolean) => void;
  onOpenRunModule: () => void;
  onRefreshWorkers: () => void;
};

export function ExplorerSidebar({
  siteName,
  onOpenRun,
  onOpenRunModule,
  onRefreshWorkers,
}: Props) {
  const ctx = useRunContext();
  const history = useHistoryContext();
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Flow | null>(null);
  const [filter, setFilter] = useState("");
  const [contextMenu, setContextMenu] = useState<{ flow: Flow; x: number; y: number } | null>(
    null,
  );
  const [setupModalFlow, setSetupModalFlow] = useState<Flow | null>(null);
  const { ask, confirmProps } = useConfirmDialog();

  const picked = history.selected.size;
  const deletable = history.runs.filter((run) => !history.isBusy(run));
  const allChecked =
    deletable.length > 0 && deletable.every((run) => history.selected.has(run.id));

  const nodes = useMemo((): ExplorerNode[] => {
    const flowNodes: ExplorerNode[] = ctx.flows.map((flow) => ({
      id: flow.id,
      kind: "flow",
      label: flow.name,
      sub: flowListSub(flow, ctx.flows),
      selected: flow.id === ctx.selectedFlowId,
      markColor: "var(--c-run)",
      pick: isConfirmedFlow(flow) ? (
        <input
          type="checkbox"
          className="pick"
          checked={ctx.selectedPicks.has(flow.id)}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => ctx.togglePick(flow.id, event.target.checked)}
        />
      ) : (
        <span className="pick" />
      ),
      onSelect: () => {
        ctx.setSelectedFlowId(flow.id);
        ctx.onLog(`选中流程 ${flow.name}`);
        onOpenRunModule();
      },
      onContextMenu: (event) => {
        ctx.setSelectedFlowId(flow.id);
        setContextMenu({ flow, x: event.clientX, y: event.clientY });
      },
      onDelete: flow.status === "draft" ? () => setDeleteTarget(flow) : undefined,
      deleteTitle: "删除草稿",
    }));

    const suiteNodes: ExplorerNode[] = ctx.suites.map((suite) => ({
      id: suite.id,
      kind: "suite",
      label: suite.name,
      sub: `${(suite.flow_ids ?? []).length} 条`,
      selected: ctx.selectedSuiteId === suite.id,
      markColor: "var(--c-record)",
      onSelect: () => {
        ctx.selectSuite(suite.id);
        onOpenRunModule();
      },
      onDelete: () =>
        ask({
          title: "删除套件",
          message: `删除套件「${suite.name}」？用例本身不会删。`,
          variant: "danger",
          onConfirm: () => ctx.deleteSuite(suite.id),
        }),
      deleteTitle: "删除套件",
    }));

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
        disabled: busy,
        pick: (
          <input
            type="checkbox"
            className="pick"
            disabled={busy}
            checked={history.selected.has(run.id)}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => history.togglePick(run.id, event.target.checked)}
          />
        ),
        onSelect: () => onOpenRun(run.id, `运行 ${run.id.slice(0, 8)}`, false),
      };
    });

    return [
      { id: "folder-flows", kind: "folder", label: "测试用例", children: flowNodes },
      { id: "folder-suites", kind: "folder", label: "套件", children: suiteNodes },
      { id: "folder-runs", kind: "folder", label: "运行记录", children: runNodes },
    ];
  }, [
    ask,
    ctx,
    history,
    onOpenRun,
    onOpenRunModule,
  ]);

  const filterActions = (
    <>
      <button
        type="button"
        className="explorer-icon-btn"
        title="从其他环境导入"
        aria-label="从其他环境导入"
        onClick={() => setImportOpen(true)}
      >
        <FolderInput size={14} strokeWidth={2} aria-hidden />
      </button>
      <button
        type="button"
        className="explorer-icon-btn"
        title="刷新运行记录"
        aria-label="刷新运行记录"
        onClick={() => {
          onRefreshWorkers();
          void history.refresh();
        }}
      >
        <RefreshCw size={13} strokeWidth={2} aria-hidden />
      </button>
      {history.runs.length > 0 ? (
        <button
          type="button"
          className="explorer-icon-btn"
          title={
            picked === 0
              ? "删除运行记录：请先在「运行记录」文件夹中勾选"
              : `删除所选运行记录（${picked} 条）`
          }
          aria-label="删除所选运行记录"
          disabled={picked === 0}
          onClick={() => void history.deleteSelected()}
        >
          <Trash2 size={13} strokeWidth={2} aria-hidden />
        </button>
      ) : null}
    </>
  );

  return (
    <>
      <Sidebar
        open
        explorer
        title={siteName ?? "未选站点"}
        body={
          <SidebarBody explorer>
            {!ctx.siteId ? (
              <EmptyState>先在顶栏选择或添加站点。</EmptyState>
            ) : (
              <>
                {history.runs.length > 0 ? (
                  <Checkbox
                    className="check hist-tools"
                    label={
                      <>
                        全选记录
                        <Muted>{picked ? `已选 ${picked}` : "未选"}</Muted>
                      </>
                    }
                    checked={allChecked}
                    onChange={(event) => history.toggleAll(event.target.checked)}
                  />
                ) : null}
                <ExplorerTree
                  nodes={nodes}
                  filter={filter}
                  onFilterChange={setFilter}
                  filterPlaceholder="Enter text to search..."
                  emptyMessage={ctx.loading ? "加载中…" : "没有匹配项"}
                  filterActions={filterActions}
                />
              </>
            )}
          </SidebarBody>
        }
        foot={
          <SidebarFoot>
            <RunSidebarFootActions onOpenRun={onOpenRun} />
          </SidebarFoot>
        }
      />
      <ImportFlowsModal open={importOpen} onClose={() => setImportOpen(false)} />
      <DeleteFlowModal flow={deleteTarget} onClose={() => setDeleteTarget(null)} />
      <ConfirmModal {...confirmProps} />
      {contextMenu ? (
        <FlowExplorerContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onConfigureSetup={() => setSetupModalFlow(contextMenu.flow)}
          onClose={() => setContextMenu(null)}
        />
      ) : null}
      <FlowSetupModal flow={setupModalFlow} onClose={() => setSetupModalFlow(null)} />
    </>
  );
}
