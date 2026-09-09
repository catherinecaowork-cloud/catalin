import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

export type ButtonVariant =
  | "default"
  | "primary"
  | "go"
  | "warn"
  | "danger"
  | "ghost"
  | "inline"
  | "bar";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
};

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  default: "cmd",
  primary: "cmd primary",
  go: "cmd go",
  warn: "cmd warn",
  danger: "cmd danger",
  ghost: "cmd ghost",
  inline: "cmd ghost inline",
  bar: "bar-btn",
};

export function Button({ variant = "default", className, type = "button", ...rest }: Props) {
  return <button type={type} className={cn(VARIANT_CLASS[variant], className)} {...rest} />;
}
