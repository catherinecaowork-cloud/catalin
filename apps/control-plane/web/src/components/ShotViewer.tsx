import { useEffect } from "react";

import { IconButton } from "./ui";

type Props = {
  open: boolean;
  url: string;
  label: string;
  index: number;
  total: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
};

export function ShotViewer({
  open,
  url,
  label,
  index,
  total,
  onClose,
  onPrev,
  onNext,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft" && index > 0) onPrev();
      if (event.key === "ArrowRight" && index < total - 1) onNext();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose, onPrev, onNext, index, total]);

  if (!open) return null;

  return (
    <div
      className="shot-viewer open"
      role="dialog"
      aria-modal="true"
      aria-label="查看截图"
      onClick={onClose}
    >
      <IconButton variant="shot-close" aria-label="关闭" onClick={onClose}>
        ×
      </IconButton>
      <IconButton
        variant="shot-nav"
        nav="prev"
        aria-label="上一张"
        disabled={index <= 0}
        onClick={(event) => {
          event.stopPropagation();
          onPrev();
        }}
      >
        ‹
      </IconButton>
      <figure onClick={(event) => event.stopPropagation()}>
        <img src={url} alt={label} />
        <figcaption>
          {index + 1} / {total} · {label}
        </figcaption>
      </figure>
      <IconButton
        variant="shot-nav"
        nav="next"
        aria-label="下一张"
        disabled={index >= total - 1}
        onClick={(event) => {
          event.stopPropagation();
          onNext();
        }}
      >
        ›
      </IconButton>
    </div>
  );
}
