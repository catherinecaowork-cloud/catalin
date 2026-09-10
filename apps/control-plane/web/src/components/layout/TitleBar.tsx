import type { ReactNode } from "react";

type Props = {
  toolbar: ReactNode;
  tabs: ReactNode;
  status: ReactNode;
};

export function TitleBar({ toolbar, tabs, status }: Props) {
  return (
    <header className="titlebar">
      <div className="brand">ATP</div>
      {toolbar}
      {tabs}
      {status}
    </header>
  );
}
