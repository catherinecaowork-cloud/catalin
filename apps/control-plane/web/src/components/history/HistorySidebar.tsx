import { useHistoryContext } from "../../context/HistoryContext";
import { ExplorerItem } from "../patterns/ExplorerItem";
import { Button, Checkbox, EmptyState, ModuleHint, Muted } from "../ui";

type Props = {
  onOpenRun: (runId: string, title: string) => void;
};

export function HistorySidebar({ onOpenRun }: Props) {
  const history = useHistoryContext();
  const picked = history.selected.size;
  const deletable = history.runs.filter((run) => !history.isBusy(run));
  const allChecked =
    deletable.length > 0 && deletable.every((run) => history.selected.has(run.id));

  return (
    <>
      <ModuleHint>勾选无用记录删除。点一行可打开直播；进行中不可删。</ModuleHint>
      <Checkbox
        className="check hist-tools"
        label={
          <>
        全选
        <Muted>{picked ? `已选 ${picked}` : "未选"}</Muted>
          </>
        }
        checked={allChecked}
        onChange={(event) => history.toggleAll(event.target.checked)}
      />
      {history.loading ? (
        <EmptyState>加载中…</EmptyState>
      ) : history.runs.length === 0 ? (
        <EmptyState>当前站点还没有运行记录。</EmptyState>
      ) : (
        history.runs.map((run) => {
          const busy = history.isBusy(run);
          const time = new Date(run.created_at).toLocaleString("zh-CN", {
            hour12: false,
          });
          const dur = run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : "";
          return (
            <ExplorerItem
              key={run.id}
              markColor="var(--c-history)"
              name={`${history.kindText(run.kind)} · ${history.statusText(run.status)}`}
              sub={`${time} ${dur}`}
              pick={
                <input
                  type="checkbox"
                  className="pick"
                  disabled={busy}
                  checked={history.selected.has(run.id)}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => history.togglePick(run.id, event.target.checked)}
                />
              }
              onSelect={() => onOpenRun(run.id, `运行 ${run.id.slice(0, 8)}`)}
            />
          );
        })
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
