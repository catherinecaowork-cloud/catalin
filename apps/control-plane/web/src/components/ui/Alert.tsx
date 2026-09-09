import type { ReactNode } from "react";

import { cn } from "./cn";

type Props = {
  children: ReactNode;
  variant?: "info" | "error";
  className?: string;
};

export function Alert({ children, variant = "info", className }: Props) {
  return (
    <div className={cn("alert", variant === "error" && "error", className)}>
      {children}
    </div>
  );
}
