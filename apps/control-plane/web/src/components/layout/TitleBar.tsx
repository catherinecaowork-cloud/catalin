import type { ReactNode } from "react";

type Props = {
  toolbar: ReactNode;
  tabs: ReactNode;
  status: ReactNode;
};

export function TitleBar({ toolbar, tabs, status }: Props) {
  return (
    <header className="titlebar">
      <div className="brand" title="Catalin">
        <span className="brand-mark" aria-hidden>
          C
        </span>
        <span className="brand-name">Catalin</span>
      </div>
      {toolbar}
      {tabs}
      {status}
    </header>
  );
}
