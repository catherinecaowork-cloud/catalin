import type { LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { cn } from "../ui";

type ToolbarProps = {
  children: ReactNode;
  color?: string;
  className?: string;
};

type GroupProps = {
  children: ReactNode;
  className?: string;
};

type ButtonProps = {
  icon: LucideIcon;
  label?: string;
  title?: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
};

type LabelProps = {
  icon?: LucideIcon;
  children: ReactNode;
};

type BadgeProps = {
  children: ReactNode;
  tone?: "ok" | "bad" | "busy" | "muted";
};

export function ModuleToolbar({ children, color, className }: ToolbarProps) {
  const style: CSSProperties | undefined = color
    ? ({ color, borderLeft: `2px solid ${color}` } as CSSProperties)
    : undefined;

  return (
    <div className={cn("editor-toolbar module-toolbar", className)} style={style}>
      {children}
    </div>
  );
}

export function ModuleToolbarGroup({ children, className }: GroupProps) {
  return <div className={cn("module-toolbar-group", className)}>{children}</div>;
}

export function ModuleToolbarSep() {
  return <span className="module-toolbar-sep" aria-hidden="true" />;
}

export function ModuleToolbarLabel({ icon: Icon, children }: LabelProps) {
  return (
    <span className="module-toolbar-label">
      {Icon ? <Icon size={14} strokeWidth={2} aria-hidden /> : null}
      <span>{children}</span>
    </span>
  );
}

export function ModuleToolbarButton({
  icon: Icon,
  label,
  title,
  active,
  disabled,
  onClick,
}: ButtonProps) {
  const text = title ?? label;
  return (
    <button
      type="button"
      className={cn("module-toolbar-btn", active && "active")}
      title={text}
      aria-label={text}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon size={14} strokeWidth={2} aria-hidden />
      {label ? <span>{label}</span> : null}
    </button>
  );
}

export function ModuleToolbarBadge({ children, tone = "muted" }: BadgeProps) {
  return <span className={cn("module-toolbar-badge", tone)}>{children}</span>;
}

export function ModuleToolbarSpacer() {
  return <span className="module-toolbar-spacer" />;
}
