import { Button, EmptyState } from "./ui";

type Props = {
  lines: string[];
  open: boolean;
  onClear: () => void;
};

export function BottomLog({ lines, open, onClear }: Props) {
  if (!open) return null;

  return (
    <div className="bottomlog open" id="bottomlog">
      <div className="loghead">
        <span>输出</span>
        <Button variant="inline" onClick={onClear}>
          清空
        </Button>
      </div>
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
  );
}
