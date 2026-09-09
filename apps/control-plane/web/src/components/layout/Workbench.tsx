import type { ReactNode } from "react";

type Props = {
  activity: ReactNode;
  sidebar: ReactNode;
  editor: ReactNode;
};

export function Workbench({ activity, sidebar, editor }: Props) {
  return (
    <div className="workbench">
      {activity}
      {sidebar}
      {editor}
    </div>
  );
}
