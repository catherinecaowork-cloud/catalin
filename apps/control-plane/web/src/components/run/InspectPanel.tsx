import type { RunAlert, RunAssert, Shot } from "../../types";
import { Tabs } from "../ui";
import { AlertPane, AssertPane } from "./InspectPanes";
import { ShotPane } from "./ShotPane";

export type InspectTab = "shot" | "alert" | "assert";

const INSPECT_TABS = [
  { id: "shot" as const, label: "画面" },
  { id: "alert" as const, label: "告警" },
  { id: "assert" as const, label: "断言" },
];

type Props = {
  tab: InspectTab;
  onTabChange: (tab: InspectTab) => void;
  shots: Shot[];
  shotIndex: number;
  onSelectShot: (index: number) => void;
  onZoomShot: () => void;
  alerts: RunAlert[];
  asserts: RunAssert[];
};

export function InspectPanel({
  tab,
  onTabChange,
  shots,
  shotIndex,
  onSelectShot,
  onZoomShot,
  alerts,
  asserts,
}: Props) {
  return (
    <aside className="split-inspect">
      <Tabs tabs={INSPECT_TABS} active={tab} onChange={onTabChange} />
      <div className="insp-body">
        {tab === "shot" ? (
          <ShotPane
            shots={shots}
            shotIndex={shotIndex}
            onSelect={onSelectShot}
            onZoom={onZoomShot}
          />
        ) : null}
        {tab === "alert" ? <AlertPane alerts={alerts} /> : null}
        {tab === "assert" ? <AssertPane asserts={asserts} /> : null}
      </div>
    </aside>
  );
}
