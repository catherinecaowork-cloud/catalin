import { useId, type ReactNode } from "react";

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
  onClose: _onClose,
  title,
  titleId: titleIdProp,
  wide,
  children,
  actions,
}: Props) {
  const autoId = useId();
  const titleId = titleIdProp ?? (title ? autoId : undefined);

  if (!open) return null;

  return (
    <div className="modal-backdrop open">
      <div
        className={cn("modal", wide && "wide")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        {title ? <h3 id={titleId}>{title}</h3> : null}
        {children}
        {actions ? <div className="actions">{actions}</div> : null}
      </div>
    </div>
  );
}
