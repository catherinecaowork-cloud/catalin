import type { ReactNode } from "react";

import { cn } from "../ui";

type Props = {
  sidebar: ReactNode;
  editor: ReactNode;
  rightPanel?: ReactNode;
};

export function Workbench({ sidebar, editor, rightPanel }: Props) {
  return (
    <div className={cn("workbench", rightPanel ? "has-right-panel" : undefined)}>
      {sidebar}
      <div className="workbench-main">{editor}</div>
      {rightPanel}
    </div>
  );
}
