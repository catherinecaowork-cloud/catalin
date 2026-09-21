import { FolderInput } from "lucide-react";
import { useMemo, useState } from "react";

import { useRunContext } from "../../context/RunContext";
import { useConfirmDialog } from "../../hooks/useConfirmDialog";
import type { Flow, Suite } from "../../types";
import { flowListSub, flowStatusText, isConfirmedFlow } from "../../utils/flow";
import { ConfirmModal } from "../patterns/ConfirmModal";
import { FlowExplorerContextMenu } from "../patterns/FlowExplorerContextMenu";
import { FlowSetupModal } from "../patterns/FlowSetupModal";
import { ExplorerTree, type ExplorerNode } from "../patterns/ExplorerTree";
import { PromptModal } from "../patterns/PromptModal";
import { Button, EmptyState, FootHint, Switch } from "../ui";
import { DeleteFlowModal } from "./DeleteFlowModal";
import { ImportFlowsModal } from "./ImportFlowsModal";

export function RunSidebar() {
  const ctx = useRunContext();
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
      onSelect: () => ctx.selectSuite(suite.id),
      onContextMenu: (event) => {
        ctx.selectSuite(suite.id);
        setContextMenu({ kind: "suite", suite, x: event.clientX, y: event.clientY });
      },
    }));

    const tree: ExplorerNode[] = [];
    if (flowNodes.length || !ctx.loading) {
      tree.push({ id: "folder-flows", kind: "folder", label: "测试用例", children: flowNodes });
    }
    if (suiteNodes.length) {
      tree.push({ id: "folder-suites", kind: "folder", label: "套件", children: suiteNodes });
    }
    return tree;
  }, [
    ctx.flows,
    ctx.flows.length,
    ctx.loading,
    ctx.onLog,
    ctx.selectedFlowId,
    ctx.selectedPicks,
    ctx.selectedSuiteId,
    ctx.setSelectedFlowId,
    ctx.suites,
    ctx.suites.length,
    ctx.selectSuite,
    ctx.togglePick,
  ]);

  if (!ctx.siteId) {
    return <EmptyState>先在顶栏选择或添加站点。</EmptyState>;
  }

  const importAction = (
    <button
      type="button"
      className="explorer-icon-btn"
      title="从其他环境导入"
      aria-label="从其他环境导入"
      onClick={() => setImportOpen(true)}
    >
      <FolderInput size={14} strokeWidth={2} aria-hidden />
    </button>
  );

  return (
    <>
      {ctx.loading ? (
        <ExplorerTree
          nodes={[]}
          filter={filter}
          onFilterChange={setFilter}
          filterPlaceholder="搜索用例或套件…"
          emptyMessage="加载中…"
          filterActions={importAction}
        />
      ) : ctx.flows.length === 0 && ctx.suites.length === 0 ? (
        <ExplorerTree
          nodes={[]}
          filter={filter}
          onFilterChange={setFilter}
          filterPlaceholder="搜索用例或套件…"
          emptyMessage="当前环境还没有脚本。到录制模块录一条，或点右侧图标导入。"
          filterActions={importAction}
        />
      ) : (
        <ExplorerTree
          nodes={nodes}
          filter={filter}
          onFilterChange={setFilter}
          filterPlaceholder="搜索用例或套件…"
          emptyMessage="没有匹配的用例或套件"
          filterActions={importAction}
        />
      )}

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

export function RunSidebarFoot({
  onStartRun,
  onStartPicked,
}: {
  onStartRun: () => void;
  onStartPicked: () => void;
}) {
  const ctx = useRunContext();
  const selectedFlow = ctx.flows.find((flow) => flow.id === ctx.selectedFlowId) ?? null;
  const pickedCount = ctx.pickedFlowIds().length;
  const [suitePromptOpen, setSuitePromptOpen] = useState(false);
  const { ask, confirmProps } = useConfirmDialog();

  const promoteLabel =
    !selectedFlow
      ? "确认为用例"
      : selectedFlow.status === "draft"
        ? "确认为用例"
        : "退回草稿";

  const promoteVariant =
    selectedFlow && selectedFlow.status !== "draft" ? "warn" : "primary";

  const hint =
    !selectedFlow
      ? "选中草稿后，确认步骤无误再标成用例。"
      : selectedFlow.status === "draft"
        ? "确认后状态从草稿变为用例。跑成功不会自动确认。"
        : `当前是${flowStatusText(selectedFlow.status)}。用例不能删除，要改或删先退回草稿。`;

  return (
    <div className="run-foot">
      <FootHint>右键测试用例 →「前置流程配置」可多选前置脚本。</FootHint>

      <Switch
        label="开窗执行"
        checked={ctx.headed}
        onChange={(event) => ctx.setHeaded(event.target.checked)}
      />
      <Switch
        label="演练（跳过写数据）"
        checked={ctx.dryRun}
        onChange={(event) => ctx.setDryRun(event.target.checked)}
      />

      <Button variant="go" disabled={!selectedFlow} onClick={onStartRun}>
        运行所选流程
      </Button>
      <Button variant="go" style={{ marginTop: 8 }} disabled={pickedCount === 0} onClick={onStartPicked}>
        运行勾选
      </Button>
      <Button
        variant="primary"
        style={{ marginTop: 8 }}
        disabled={pickedCount === 0}
        onClick={() => setSuitePromptOpen(true)}
      >
        存成套件
      </Button>
      <Button
        variant={promoteVariant}
        style={{ marginTop: 8 }}
        disabled={!selectedFlow}
        onClick={() => {
          if (!selectedFlow) return;
          const toDraft = selectedFlow.status !== "draft";
          ask({
            title: toDraft ? "退回草稿" : "确认为用例",
            message: toDraft
              ? `将「${selectedFlow.name}」退回草稿？退回后才能删除。`
              : `确认「${selectedFlow.name}」的步骤符合业务意图，将它标为用例？`,
            variant: toDraft ? "warn" : "primary",
            onConfirm: () => ctx.promoteFlow(selectedFlow),
          });
        }}
      >
        {promoteLabel}
      </Button>
      <FootHint>{hint}</FootHint>

      <PromptModal
        open={suitePromptOpen}
        title="保存套件"
        label="套件名称"
        defaultValue="造完整款式"
        onCancel={() => setSuitePromptOpen(false)}
        onConfirm={async (name) => {
          await ctx.saveSuite(name);
          setSuitePromptOpen(false);
        }}
      />
      <ConfirmModal {...confirmProps} />
    </div>
  );
}

export function RunSidebarFootActions({
  onOpenRun,
}: {
  onOpenRun: (runId: string, title: string, headed: boolean) => void;
}) {
  const ctx = useRunContext();

  return (
    <RunSidebarFoot
      onStartRun={() => {
        void ctx
          .startSingleRun()
          .then(({ runId, title }) => {
            onOpenRun(runId, title, ctx.headed);
          })
          .catch((err) => ctx.onLog(err instanceof Error ? err.message : String(err), "error"));
      }}
      onStartPicked={() => {
        void ctx
          .startPickedRuns()
          .then(({ batch, title }) => {
            if (!batch.current_run_id) {
              ctx.onLog("批次未生成运行", "error");
              return;
            }
            onOpenRun(batch.current_run_id, title, ctx.headed);
          })
          .catch((err) => ctx.onLog(err instanceof Error ? err.message : String(err), "error"));
      }}
    />
  );
}
