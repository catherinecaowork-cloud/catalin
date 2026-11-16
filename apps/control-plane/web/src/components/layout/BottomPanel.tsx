import { Button, EmptyState } from "../ui";

type Props = {
  lines: string[];
  open: boolean;
  onClear: () => void;
  onToggle: () => void;
};

/** 底栏只保留「输出」日志，避免与主区步骤表 / 检视面板重复。 */
export function BottomPanel({ lines, open, onClear, onToggle }: Props) {
  if (!open) return null;

  return (
    <div className="bottom-panel open" id="bottomlog">
      <div className="bottom-panel-head">
        <div className="bottom-panel-tabs" role="tablist">
          <button type="button" role="tab" className="on" aria-selected>
            输出
          </button>
        </div>
        <div className="bottom-panel-actions">
          <Button variant="inline" onClick={onClear}>
            清空
          </Button>
          <Button variant="inline" title="收起底栏" onClick={onToggle}>
            ×
          </Button>
        </div>
      </div>
      <div className="bottom-panel-body">
        <div className="logview" id="logview">
          {lines.length === 0 ? (
            <EmptyState>日志会显示在这里。</EmptyState>
          ) : (
            lines.map((line, index) => (
              <div key={`${index}-${line.slice(0, 24)}`}>{line}</div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
