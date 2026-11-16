import { Bot, Play, Square, Terminal } from "lucide-react";

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
  onToggleLog: () => void;
  logOpen: boolean;
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
  onToggleLog,
  logOpen,
}: Props) {
  const badgeClass = phase ? "busy" : online ? "ok" : "bad";

  return (
    <div className="statusbits" aria-label="状态与工具">
      <span className={cn("worker-badge", badgeClass)} title={badge}>
        {badge}
      </span>

      <div className="statusbits-tools" role="group" aria-label="辅助工具">
        <button
          type="button"
          className="bar-btn bar-btn-icon"
          title="启动 Worker"
          aria-label="启动 Worker"
          disabled={busy}
          onClick={onStart}
        >
          <Play size={13} aria-hidden strokeWidth={2} />
        </button>
        <button
          type="button"
          className="bar-btn bar-btn-icon"
          title="停止 Worker"
          aria-label="停止 Worker"
          disabled={busy || phase === "stopping"}
          onClick={onStop}
        >
          <Square size={12} aria-hidden strokeWidth={2} />
        </button>
        <button
          type="button"
          className="bar-btn bar-btn-icon"
          title="配置模型网关"
          aria-label="配置 AI 网关"
          onClick={onOpenAiConfig}
        >
          <Bot size={13} aria-hidden strokeWidth={2} />
        </button>
        <button
          type="button"
          className={cn("bar-btn", "bar-btn-icon", logOpen && "active")}
          title={logOpen ? "收起输出" : "展开输出"}
          aria-label={logOpen ? "收起输出" : "展开输出"}
          onClick={onToggleLog}
        >
          <Terminal size={13} aria-hidden strokeWidth={2} />
        </button>
      </div>

      {aiBadge ? (
        <span className="muted ai-badge" title={aiBadge}>
          {aiBadge}
        </span>
      ) : null}
    </div>
  );
}
