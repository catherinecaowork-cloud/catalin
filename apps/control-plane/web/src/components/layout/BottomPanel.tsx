import { useMemo, useState } from "react";

import { useBottomPanel } from "../../context/BottomPanelContext";
import { AlertPane } from "../run/InspectPanes";
import { StepTable } from "../run/StepTable";
import { Button, EmptyState } from "../ui";

type TabId = "output" | "steps" | "alerts";

type Props = {
  lines: string[];
  open: boolean;
  onClear: () => void;
  onToggle: () => void;
};

const TABS: { id: TabId; label: string }[] = [
  { id: "output", label: "输出" },
  { id: "steps", label: "步骤" },
  { id: "alerts", label: "告警" },
];

export function BottomPanel({ lines, open, onClear, onToggle }: Props) {
  const { feed } = useBottomPanel();
  const [tab, setTab] = useState<TabId>("output");

  const alertCount = feed.alerts.length;
  const stepCount = feed.steps.length;

  const tabs = useMemo(
    () =>
      TABS.map((item) => ({
        ...item,
        badge:
          item.id === "steps" && stepCount
            ? String(stepCount)
            : item.id === "alerts" && alertCount
              ? String(alertCount)
              : null,
      })),
    [alertCount, stepCount],
  );

  if (!open) return null;

  return (
    <div className="bottom-panel open" id="bottomlog">
      <div className="bottom-panel-head">
        <div className="bottom-panel-tabs" role="tablist">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              className={tab === item.id ? "on" : undefined}
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
            >
              {item.label}
              {item.badge ? <span className="bottom-tab-badge">{item.badge}</span> : null}
            </button>
          ))}
        </div>
        <div className="bottom-panel-actions">
          {tab === "output" ? (
            <Button variant="inline" onClick={onClear}>
              清空
            </Button>
          ) : null}
          <Button variant="inline" title="收起底栏" onClick={onToggle}>
            ×
          </Button>
        </div>
      </div>
      <div className="bottom-panel-body">
        {tab === "output" ? (
          <div className="logview" id="logview">
            {lines.length === 0 ? (
              <EmptyState>日志会显示在这里。</EmptyState>
            ) : (
              lines.map((line, index) => (
                <div key={`${index}-${line.slice(0, 24)}`}>{line}</div>
              ))
            )}
          </div>
        ) : null}
        {tab === "steps" ? (
          <div className="bottom-panel-scroll">
            <StepTable steps={feed.steps} />
          </div>
        ) : null}
        {tab === "alerts" ? (
          <div className="bottom-panel-scroll">
            <AlertPane alerts={feed.alerts} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
