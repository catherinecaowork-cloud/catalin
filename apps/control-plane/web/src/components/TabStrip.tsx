import type { EditorTab } from "../types";
import { MODULES } from "../types";
import { cn, IconButton } from "./ui";

type Props = {
  tabs: EditorTab[];
  activeTabId: string | null;
  onSelect: (tabId: string) => void;
  onClose: (tabId: string) => void;
};

export function TabStrip({ tabs, activeTabId, onSelect, onClose }: Props) {
  return (
    <div className="tabstrip" role="tablist">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          className={cn("etab", `kind-${tab.kind}`, tab.id === activeTabId && "active")}
          onClick={() => onSelect(tab.id)}
          onKeyDown={(event) => event.key === "Enter" && onSelect(tab.id)}
          role="tab"
          tabIndex={0}
          aria-selected={tab.id === activeTabId}
        >
          <span className="dot" style={{ background: MODULES[tab.kind].color }} />
          {tab.title}
          <IconButton
            variant="plain"
            className="x"
            aria-label="关闭标签"
            onClick={(event) => {
              event.stopPropagation();
              onClose(tab.id);
            }}
          >
            ×
          </IconButton>
        </div>
      ))}
    </div>
  );
}
