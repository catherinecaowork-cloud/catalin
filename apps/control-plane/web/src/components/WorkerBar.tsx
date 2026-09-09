import { Bot, Play, Square } from "lucide-react";

import { cn } from "./ui";

type Props = {
  badge: string;
  phase: "starting" | "stopping" | null;
  online: boolean;
  busy: boolean;
  aiBadge: string;
  onStart: () => void;
  onStop: () => void;
  onOpenAiConfig: () => void;
};

export function WorkerBar({
  badge,
  phase,
  online,
  busy,
  aiBadge,
  onStart,
  onStop,
  onOpenAiConfig,
}: Props) {
  const badgeClass = phase ? "busy" : online ? "ok" : "bad";

  return (
    <div className="statusbits">
      <span className={cn("worker-badge", badgeClass)} title={badge}>
        {badge}
      </span>
      <button
        type="button"
        className="bar-btn bar-btn-icon"
        title="启动 Worker"
        aria-label="启动 Worker"
        disabled={busy}
        onClick={onStart}
      >
        <Play size={14} aria-hidden strokeWidth={2} />
      </button>
      <button
        type="button"
        className="bar-btn bar-btn-icon"
        title="停止 Worker"
        aria-label="停止 Worker"
        disabled={busy || phase === "stopping"}
        onClick={onStop}
      >
        <Square size={13} aria-hidden strokeWidth={2} />
      </button>
      <button
        type="button"
        className="bar-btn bar-btn-icon"
        title="配置模型网关"
        aria-label="配置 AI 网关"
        onClick={onOpenAiConfig}
      >
        <Bot size={14} aria-hidden strokeWidth={2} />
      </button>
      {aiBadge ? (
        <span className="muted ai-badge" title={aiBadge}>
          {aiBadge}
        </span>
      ) : null}
    </div>
  );
}
