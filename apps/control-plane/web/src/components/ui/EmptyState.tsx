import type { ReactNode } from "react";

import { cn } from "./cn";

type Props = {
  children: ReactNode;
  variant?: "default" | "error";
  className?: string;
};

export function EmptyState({ children, variant = "default", className }: Props) {
  return (
    <div className={cn("empty", variant === "error" && "alert error", className)}>
      {children}
    </div>
  );
}
