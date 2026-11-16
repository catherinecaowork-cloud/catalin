import { FolderInput, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { useHistoryContext } from "../../context/HistoryContext";
import { useRunContext } from "../../context/RunContext";
import type { Flow, Suite } from "../../types";
import { flowListSub, isConfirmedFlow } from "../../utils/flow";
import { ConfirmModal } from "../patterns/ConfirmModal";
import { FlowExplorerContextMenu } from "../patterns/FlowExplorerContextMenu";
import { FlowSetupModal } from "../patterns/FlowSetupModal";
import { ExplorerTree, type ExplorerNode } from "../patterns/ExplorerTree";
import { PromptModal } from "../patterns/PromptModal";
import { useConfirmDialog } from "../../hooks/useConfirmDialog";
import { Sidebar, SidebarBody, SidebarFoot } from "../layout/Sidebar";
import { EmptyState } from "../ui";
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
  const [contextMenu, setContextMenu] = useState<
    | { kind: "flow"; flow: Flow; x: number; y: number }
    | { kind: "suite"; suite: Suite; x: number; y: number }
    | null
  >(null);
  const [setupModalFlow, setSetupModalFlow] = useState<Flow | null>(null);
  const [renameTarget, setRenameTarget] = useState<
    { kind: "flow"; flow: Flow } | { kind: "suite"; suite: Suite } | null
  >(null);
  const { ask, confirmProps } = useConfirmDialog();

  const picked = history.selected.size;

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
      ) : undefined,
      onSelect: () => {
        ctx.setSelectedFlowId(flow.id);
        ctx.onLog(`选中流程 ${flow.name}`);
        onOpenRunModule();
      },
      onContextMenu: (event) => {
        ctx.setSelectedFlowId(flow.id);
        setContextMenu({ kind: "flow", flow, x: event.clientX, y: event.clientY });
      },
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
      onContextMenu: (event) => {
        ctx.selectSuite(suite.id);
        setContextMenu({ kind: "suite", suite, x: event.clientX, y: event.clientY });
      },
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
        selected: history.selected.has(run.id),
        disabled: busy,
        onSelect: (event) => {
          const additive = Boolean(event?.ctrlKey || event?.metaKey);
          const range = Boolean(event?.shiftKey);
          history.selectRun(run.id, { additive, range });
          if (!additive && !range) {
            onOpenRun(run.id, `运行 ${run.id.slice(0, 8)}`, false);
          }
        },
      };
    });

    return [
      { id: "folder-flows", kind: "folder", label: "测试用例", children: flowNodes },
      { id: "folder-suites", kind: "folder", label: "套件", children: suiteNodes },
      {
        id: "folder-runs",
        kind: "folder",
        label: "运行记录",
        sub: picked ? `${runNodes.length} · 已选 ${picked}` : String(runNodes.length),
        children: runNodes,
      },
    ];
  }, [
    ctx,
    history,
    onOpenRun,
    onOpenRunModule,
    picked,
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
              ? "删除运行记录：单击选中，Ctrl 单击加选，Shift 单击选区间，Ctrl+A 全选"
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
              <ExplorerTree
                nodes={nodes}
                filter={filter}
                onFilterChange={setFilter}
                filterPlaceholder="搜索用例、套件或记录…"
                emptyMessage={ctx.loading ? "加载中…" : "没有匹配项"}
                filterActions={filterActions}
                onSelectAll={history.selectAll}
              />
            )}
          </SidebarBody>
        }
        foot={
          ctx.siteId ? (
            <SidebarFoot>
              <RunSidebarFootActions onOpenRun={onOpenRun} />
            </SidebarFoot>
          ) : undefined
        }
      />
      <ImportFlowsModal open={importOpen} onClose={() => setImportOpen(false)} />
      <DeleteFlowModal flow={deleteTarget} onClose={() => setDeleteTarget(null)} />
      <ConfirmModal {...confirmProps} />
      {contextMenu?.kind === "flow" ? (
        <FlowExplorerContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onRename={() => setRenameTarget({ kind: "flow", flow: contextMenu.flow })}
          onConfigureSetup={() => setSetupModalFlow(contextMenu.flow)}
          onDelete={
            contextMenu.flow.status === "draft"
              ? () => setDeleteTarget(contextMenu.flow)
              : undefined
          }
          deleteLabel="删除草稿"
          onClose={() => setContextMenu(null)}
        />
      ) : null}
      {contextMenu?.kind === "suite" ? (
        <FlowExplorerContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onRename={() => setRenameTarget({ kind: "suite", suite: contextMenu.suite })}
          onDelete={() =>
            ask({
              title: "删除套件",
              message: `删除套件「${contextMenu.suite.name}」？用例本身不会删。`,
              variant: "danger",
              onConfirm: () => ctx.deleteSuite(contextMenu.suite.id),
            })
          }
          deleteLabel="删除套件"
          onClose={() => setContextMenu(null)}
        />
      ) : null}
      <PromptModal
        open={renameTarget != null}
        title="修改名称"
        label="名称"
        defaultValue={
          renameTarget?.kind === "flow"
            ? renameTarget.flow.name
            : renameTarget?.kind === "suite"
              ? renameTarget.suite.name
              : ""
        }
        confirmLabel="保存"
        onCancel={() => setRenameTarget(null)}
        onConfirm={async (name) => {
          if (!renameTarget) return;
          if (renameTarget.kind === "flow") {
            await ctx.renameFlow(renameTarget.flow, name);
          } else {
            await ctx.renameSuite(renameTarget.suite, name);
          }
          setRenameTarget(null);
        }}
      />
      <FlowSetupModal flow={setupModalFlow} onClose={() => setSetupModalFlow(null)} />
    </>
  );
}
