import type { ReactNode } from "react";

import { cn } from "../ui";

type Props = {
  children: ReactNode;
  footer?: ReactNode;
};

export function EditorLayout({ children, footer }: Props) {
  return (
    <section className="editor">
      {children}
      {footer}
    </section>
  );
}

export function EditorEmpty({ title, subtitle, hint }: { title: string; subtitle?: string; hint: string }) {
  return (
    <div className="editor-empty">
      <h2>{title}</h2>
      {subtitle ? <p className="muted">{subtitle}</p> : null}
      <p>{hint}</p>
    </div>
  );
}

export function EditorView({
  toolbar,
  color,
  children,
  bodyClassName,
}: {
  toolbar: string;
  color: string;
  children: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <div className="editor-view active">
      <div className="editor-toolbar" style={{ color }}>
        {toolbar}
      </div>
      <div className={cn("editor-body", bodyClassName)}>{children}</div>
    </div>
  );
}

export function EditorPlaceholder({ text }: { text: string }) {
  return (
    <div className="placeholder">
      <p>{text}</p>
    </div>
  );
}
