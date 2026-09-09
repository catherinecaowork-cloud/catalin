import type { ReactNode } from "react";

import { cn } from "./cn";

type Props = {
  children: ReactNode;
  className?: string;
};

export function Muted({ children, className }: Props) {
  return <span className={cn("muted", className)}>{children}</span>;
}

export function ModuleHint({ children }: Props) {
  return <p className="muted module-hint">{children}</p>;
}

export function SectionTitle({ children }: Props) {
  return (
    <p className="muted" style={{ marginBottom: 6 }}>
      {children}
    </p>
  );
}

export function FootHint({ children }: Props) {
  return <p className="muted foot-hint">{children}</p>;
}
