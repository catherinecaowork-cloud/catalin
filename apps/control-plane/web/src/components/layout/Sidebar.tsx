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
        <b>{explorer ? "资源树" : title}</b>
        {explorer && title ? <span className="side-head-sub">{title}</span> : null}
      </div>
      {/* 资源树：执行动作靠上，树体占满剩余高度，避免头顶空白、脚部拥挤 */}
      {explorer && foot ? <div className="side-actions">{foot}</div> : null}
      {body}
      {!explorer ? foot : null}
    </aside>
  );
}

export function SidebarBody({ children, explorer }: { children: ReactNode; explorer?: boolean }) {
  return <div className={cn("side-body", explorer && "explorer-body")}>{children}</div>;
}

export function SidebarFoot({ children }: { children: ReactNode }) {
  return <div className="side-foot">{children}</div>;
}
