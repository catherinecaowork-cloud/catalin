import type { ReactNode } from "react";

export type TabItem<T extends string> = {
  id: T;
  label: ReactNode;
};

type Props<T extends string> = {
  tabs: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  className?: string;
};

export function Tabs<T extends string>({ tabs, active, onChange, className = "insp-tabs" }: Props<T>) {
  return (
    <div className={className}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={active === tab.id ? "on" : ""}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
