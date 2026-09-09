import { Button } from "./ui";

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
      <span className={badgeClass}>{badge}</span>
      <Button variant="bar" disabled={busy} onClick={onStart}>
        开始
      </Button>
      <Button variant="bar" disabled={busy || phase === "stopping"} onClick={onStop}>
        停止
      </Button>
      <Button variant="bar" title="配置模型网关" onClick={onOpenAiConfig}>
        AI
      </Button>
      <span className="muted">{aiBadge}</span>
    </div>
  );
}
