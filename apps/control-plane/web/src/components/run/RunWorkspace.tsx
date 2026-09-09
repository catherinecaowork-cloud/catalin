import { useCallback, useEffect, useRef, useState } from "react";

import { useBottomPanelPublisher } from "../../context/BottomPanelContext";
import { HealModal } from "../HealModal";
import { ShotViewer } from "../ShotViewer";
import { useRunStream } from "../../hooks/useRunStream";
import type { Batch, HealTask, Worker } from "../../types";
import { InspectPanel, type InspectTab } from "./InspectPanel";
import { RunSummaryCard } from "./RunSummaryCard";
import { RunToolbar } from "./RunToolbar";
import { StepList } from "./StepList";

type Props = {
  runId: string;
  title: string;
  moduleColor?: string;
  workersOnline: boolean;
  workers: Worker[];
  headedRequested: boolean;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  onFollowBatch?: (runId: string, title: string) => void;
  onRunEnd?: () => void;
};

export function RunWorkspace({
  runId,
  title,
  moduleColor = "var(--c-run)",
  workersOnline,
  workers,
  headedRequested,
  onLog,
  onFollowBatch,
  onRunEnd,
}: Props) {
  const onFollowBatchRef = useRef(onFollowBatch);
  onFollowBatchRef.current = onFollowBatch;

  const handleFollowBatch = useCallback((batch: Batch, batchTitle: string) => {
    if (batch.current_run_id) {
      onFollowBatchRef.current?.(batch.current_run_id, batchTitle);
    }
  }, []);

  const stream = useRunStream(runId, onLog, handleFollowBatch, onRunEnd);
  useBottomPanelPublisher(stream.steps, stream.alerts);
  const [inspectTab, setInspectTab] = useState<InspectTab>("shot");
  const [viewerOpen, setViewerOpen] = useState(false);
  const [healTask, setHealTask] = useState<HealTask | null>(null);
  const promptedHealRef = useRef<string | null>(null);

  useEffect(() => {
    const task = stream.healTask;
    if (
      task &&
      task.status === "pending" &&
      task.patches?.length &&
      promptedHealRef.current !== task.id
    ) {
      promptedHealRef.current = task.id;
      setHealTask(task);
    }
  }, [stream.healTask]);

  const headedOnline = workers.filter(
    (worker) => worker.online && worker.labels?.includes("headed"),
  ).length;
  const waitingMessage = !workersOnline
    ? "没有在线执行器。请在本机启动 runner worker。"
    : headedRequested && !headedOnline
      ? "需要开窗，但在线执行器都不能开窗。"
      : stream.waitingHint;

  const currentShot = stream.shots[stream.shotIndex];

  const openStepShot = (stepId: string) => {
    const index = stream.shots.findIndex((shot) => shot.stepId === stepId);
    if (index >= 0) stream.setShotIndex(index);
    setInspectTab("shot");
  };

  return (
    <>
      <div className="run-workspace">
        <RunToolbar title={title} color={moduleColor} badge={stream.badge} />
        <div className="split">
          <div className="split-main run-steps-pane">
            {stream.summary ? (
              <RunSummaryCard
                status={stream.summary.status}
                summary={stream.summary.summary}
                durationSeconds={stream.summary.duration_seconds}
              />
            ) : null}

            <StepList
              steps={stream.steps}
              workersOnline={workersOnline}
              waitingMessage={waitingMessage}
              onOpenStepShot={openStepShot}
            />
          </div>

          <InspectPanel
            tab={inspectTab}
            onTabChange={setInspectTab}
            shots={stream.shots}
            shotIndex={stream.shotIndex}
            onSelectShot={stream.setShotIndex}
            onZoomShot={() => setViewerOpen(true)}
            alerts={stream.alerts}
            asserts={stream.asserts}
          />
        </div>
      </div>

      {currentShot ? (
        <ShotViewer
          open={viewerOpen}
          url={currentShot.url}
          label={currentShot.label}
          index={stream.shotIndex}
          total={stream.shots.length}
          onClose={() => setViewerOpen(false)}
          onPrev={() => stream.setShotIndex(Math.max(0, stream.shotIndex - 1))}
          onNext={() =>
            stream.setShotIndex(Math.min(stream.shots.length - 1, stream.shotIndex + 1))
          }
        />
      ) : null}

      <HealModal task={healTask} onClose={() => setHealTask(null)} onLog={onLog} />
    </>
  );
}
