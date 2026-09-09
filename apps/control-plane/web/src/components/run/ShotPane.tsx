import type { Shot } from "../../types";
import { EmptyState } from "../ui";

type Props = {
  shots: Shot[];
  shotIndex: number;
  onSelect: (index: number) => void;
  onZoom: () => void;
};

export function ShotPane({ shots, shotIndex, onSelect, onZoom }: Props) {
  if (!shots.length) {
    return <EmptyState>运行或录制时显示截图。</EmptyState>;
  }

  const current = shots[shotIndex] ?? shots[shots.length - 1];

  return (
    <div className="shot-pane">
      <div className="shot-meta">
        {shotIndex + 1} / {shots.length} · {current.label}
      </div>
      <img className="shot" src={current.url} alt={current.label} onClick={onZoom} />
      <div className="shot-strip">
        {shots.map((shot, index) => (
          <img
            key={shot.url}
            src={shot.url}
            alt=""
            className={index === shotIndex ? "on" : ""}
            onClick={() => onSelect(index)}
          />
        ))}
      </div>
    </div>
  );
}
