import type { ReactNode } from "react";

import { cn } from "../ui";

type Props = {
  open: boolean;
  title: ReactNode;
  body: ReactNode;
  foot?: ReactNode;
};

export function Sidebar({ open, title, body, foot }: Props) {
  return (
    <aside className={cn("sidebar", open && "open")}>
      <div className="side-head">
        <b>{title}</b>
      </div>
      {body}
      {foot}
    </aside>
  );
}

export function SidebarBody({ children }: { children: ReactNode }) {
  return <div className="side-body">{children}</div>;
}

export function SidebarFoot({ children }: { children: ReactNode }) {
  return <div className="side-foot">{children}</div>;
}
