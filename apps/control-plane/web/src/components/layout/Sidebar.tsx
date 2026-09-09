import type { ReactNode } from "react";

import { cn } from "../ui";

type Props = {
  open: boolean;
  title: ReactNode;
  body: ReactNode;
  foot?: ReactNode;
  explorer?: boolean;
};

export function Sidebar({ open, title, body, foot, explorer }: Props) {
  return (
    <aside className={cn("sidebar", open && "open", explorer && "explorer")}>
      <div className="side-head">
        <b>{explorer ? "Tests Explorer" : title}</b>
        {explorer ? <span className="side-head-sub">{title}</span> : null}
      </div>
      {body}
      {foot}
    </aside>
  );
}

export function SidebarBody({ children, explorer }: { children: ReactNode; explorer?: boolean }) {
  return <div className={cn("side-body", explorer && "explorer-body")}>{children}</div>;
}

export function SidebarFoot({ children }: { children: ReactNode }) {
  return <div className="side-foot">{children}</div>;
}
