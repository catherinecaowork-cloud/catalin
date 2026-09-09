import { useState } from "react";

import { useRunContext } from "../../context/RunContext";
import { useConfirmDialog } from "../../hooks/useConfirmDialog";
import type { Flow } from "../../types";
import { flowListSub, flowStatusText, isConfirmedFlow } from "../../utils/flow";
import { ConfirmModal } from "../patterns/ConfirmModal";
import { ExplorerItem } from "../patterns/ExplorerItem";
import { PromptModal } from "../patterns/PromptModal";
import { Button, EmptyState, Field, FootHint, ModuleHint, Select, Switch } from "../ui";
import { DeleteFlowModal } from "./DeleteFlowModal";
import { ImportFlowsModal } from "./ImportFlowsModal";

export function RunSidebar() {
  const ctx = useRunContext();
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Flow | null>(null);
  const { ask, confirmProps } = useConfirmDialog();

  if (!ctx.siteId) {
    return <EmptyState>先在顶栏选择或添加站点。</EmptyState>;
  }

  return (
    <>
      <ModuleHint>
        只显示当前环境的脚本。要用别处录的，先导入再跑。勾选已确认用例可一次按序跑，或存成套件。
      </ModuleHint>
      <Button variant="ghost" onClick={() => setImportOpen(true)}>
        从其他环境导入
      </Button>

      {ctx.suites.length > 0 ? (
        <div className="suite-block">
          <div className="explorer-label">套件</div>
          {ctx.suites.map((suite) => (
            <ExplorerItem
              key={suite.id}
              selected={ctx.selectedSuiteId === suite.id}
              markColor="var(--c-record)"
              name={suite.name}
              sub={`${(suite.flow_ids ?? []).length} 条`}
              onSelect={() => ctx.selectSuite(suite.id)}
              onDelete={() =>
                ask({
                  title: "删除套件",
                  message: `删除套件「${suite.name}」？用例本身不会删。`,
                  variant: "danger",
                  onConfirm: () => ctx.deleteSuite(suite.id),
                })
              }
              deleteTitle="删除套件"
            />
          ))}
        </div>
      ) : null}

      <div className="flow-block">
        {ctx.loading ? (
          <EmptyState>加载中…</EmptyState>
        ) : ctx.flows.length === 0 ? (
          <EmptyState>当前环境还没有脚本。到录制模块录一条，或从其他环境导入。</EmptyState>
        ) : (
          ctx.flows.map((flow) => (
            <ExplorerItem
              key={flow.id}
              selected={flow.id === ctx.selectedFlowId}
              markColor="var(--c-run)"
              name={flow.name}
              sub={flowListSub(flow, ctx.flows)}
              pick={
                isConfirmedFlow(flow) ? (
                  <input
                    type="checkbox"
                    className="pick"
                    checked={ctx.selectedPicks.has(flow.id)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => ctx.togglePick(flow.id, event.target.checked)}
                  />
                ) : (
                  <span className="pick" />
                )
              }
              onSelect={() => {
                ctx.setSelectedFlowId(flow.id);
                ctx.onLog(`选中流程 ${flow.name}`);
              }}
              onDelete={
                flow.status === "draft"
                  ? () => setDeleteTarget(flow)
                  : undefined
              }
            />
          ))
        )}
      </div>

      <ImportFlowsModal open={importOpen} onClose={() => setImportOpen(false)} />
      <DeleteFlowModal flow={deleteTarget} onClose={() => setDeleteTarget(null)} />
      <ConfirmModal {...confirmProps} />
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
  const others = ctx.flows.filter((flow) => flow.id !== selectedFlow?.id);
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
      {selectedFlow ? (
        <>
          <Field label="前置脚本">
            <Select
              value={selectedFlow.setup_flow_id ?? ""}
              onChange={(event) =>
                void ctx.updateSetup(selectedFlow.id, event.target.value || null)
              }
            >
              <option value="">无前置（单独跑）</option>
              {others.map((flow) => (
                <option key={flow.id} value={flow.id}>
                  {flow.name} · {flowStatusText(flow.status)}
                </option>
              ))}
            </Select>
          </Field>
          <FootHint>有前置时先跑前置再跑本条，浏览器不关、只登录一次。套件同样。</FootHint>
        </>
      ) : null}

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
