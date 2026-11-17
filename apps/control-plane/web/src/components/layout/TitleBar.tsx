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
        <img className="brand-mark" src="/favicon.svg" width={18} height={18} alt="" />
        <span className="brand-name">Catalin</span>
      </div>
      {toolbar}
      {tabs}
      {status}
    </header>
  );
}
