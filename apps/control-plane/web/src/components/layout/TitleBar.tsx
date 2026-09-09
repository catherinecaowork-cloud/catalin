import type { ReactNode } from "react";

type Props = {
  site: ReactNode;
  tabs: ReactNode;
  status: ReactNode;
};

export function TitleBar({ site, tabs, status }: Props) {
  return (
    <header className="titlebar">
      <div className="brand">ATP</div>
      {site}
      {tabs}
      {status}
    </header>
  );
}
