import { useEffect, useId, type ReactNode } from "react";

import { cn } from "./cn";

type Props = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  titleId?: string;
  wide?: boolean;
  children: ReactNode;
  actions?: ReactNode;
};

export function Modal({
  open,
  onClose,
  title,
  titleId: titleIdProp,
  wide,
  children,
  actions,
}: Props) {
  const autoId = useId();
  const titleId = titleIdProp ?? (title ? autoId : undefined);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-backdrop open" onClick={onClose}>
      <div
        className={cn("modal", wide && "wide")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        {title ? <h3 id={titleId}>{title}</h3> : null}
        {children}
        {actions ? <div className="actions">{actions}</div> : null}
      </div>
    </div>
  );
}
