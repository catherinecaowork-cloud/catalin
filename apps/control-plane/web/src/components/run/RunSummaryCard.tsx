import { statusText } from "../../utils/flow";

type Props = {
  status: string;
  summary: Record<string, unknown> | null;
  durationSeconds: number | null;
};

export function RunSummaryCard({ status, summary, durationSeconds }: Props) {
  return (
    <div className="card run-summary">
      <div className={`result ${status}`}>{statusText(status)}</div>
      <div className="muted">
        通过 {String(summary?.passed ?? 0)} · 失败 {String(summary?.failed ?? 0)} · 跳过{" "}
        {String(summary?.skipped ?? 0)}
        {durationSeconds ? ` · ${durationSeconds.toFixed(1)}s` : ""}
      </div>
    </div>
  );
}
