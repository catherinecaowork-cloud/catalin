import type { KeyboardEvent, MouseEvent, ReactNode } from "react";

import { cn, IconButton } from "../ui";

type Props = {
  selected?: boolean;
  markColor: string;
  name: ReactNode;
  sub?: ReactNode;
  pick?: ReactNode;
  onSelect?: () => void;
  onDelete?: () => void;
  deleteTitle?: string;
  className?: string;
};

export function ExplorerItem({
  selected,
  markColor,
  name,
  sub,
  pick,
  onSelect,
  onDelete,
  deleteTitle = "删除",
  className,
}: Props) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter") onSelect?.();
  };

  const stop = (event: MouseEvent) => event.stopPropagation();

  return (
    <div
      className={cn("explorer-item", selected && "selected", className)}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
    >
      {pick ?? <span className="pick" />}
      <span className="mark" style={{ background: markColor }} />
      <span className="name">{name}</span>
      {sub ? <span className="sub">{sub}</span> : null}
      {onDelete ? (
        <IconButton
          variant="del"
          title={deleteTitle}
          onClick={(event) => {
            stop(event);
            onDelete();
          }}
        >
          ×
        </IconButton>
      ) : null}
    </div>
  );
}
