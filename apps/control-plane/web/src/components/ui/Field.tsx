import type { ReactNode } from "react";

type Props = {
  label?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Field({ label, children, className = "field" }: Props) {
  return (
    <div className={className}>
      {label ? <span>{label}</span> : null}
      {children}
    </div>
  );
}
