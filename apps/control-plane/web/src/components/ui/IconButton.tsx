import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "del" | "shot-close" | "shot-nav" | "plain";
  nav?: "prev" | "next";
  children: ReactNode;
};

export function IconButton({
  variant = "del",
  nav,
  className,
  type = "button",
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={cn(
        variant === "del" && "del",
        variant === "shot-close" && "shot-viewer-close",
        variant === "shot-nav" && cn("shot-viewer-nav", nav),
        className,
      )}
      {...rest}
    />
  );
}
