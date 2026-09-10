import { CircleDot, Pause, Play, Square, Terminal } from "lucide-react";

import { useRecordContext } from "../../context/RecordContext";
import { cn } from "../ui";

type Props = {
  onLaunchRecord: () => void;
  onOpenRun: () => void;
  onToggleLog: () => void;
  logOpen: boolean;
};

export function MainToolbar({ onLaunchRecord, onOpenRun, onToggleLog, logOpen }: Props) {
  const record = useRecordContext();
  const recording = record.stage === "busy";

  return (
    <div className="main-toolbar titlebar-toolbar" role="toolbar" aria-label="主操作">
      <div className="main-toolbar-group">
        <button
          type="button"
          className={cn("main-toolbar-btn", "record", recording && "busy")}
          title={recording ? "结束录制" : "录制 Web"}
          aria-label={recording ? "结束录制" : "录制 Web"}
          onClick={() => {
            if (recording) {
              void record.stopRecord();
              return;
            }
            onLaunchRecord();
          }}
        >
          <span className="main-toolbar-icon">
            {recording ? (
              <Square size={14} strokeWidth={2} aria-hidden />
            ) : (
              <CircleDot size={15} strokeWidth={2} aria-hidden />
            )}
            {!recording ? <span className="main-toolbar-rec-dot" aria-hidden /> : null}
          </span>
        </button>

        {recording ? (
          <button
            type="button"
            className={cn("main-toolbar-btn", record.recordPaused && "active")}
            title={record.recordPaused ? "继续录制" : "暂停录制"}
            aria-label={record.recordPaused ? "继续录制" : "暂停录制"}
            onClick={() => void record.toggleRecordPause()}
          >
            <span className="main-toolbar-icon">
              {record.recordPaused ? (
                <Play size={14} strokeWidth={2} aria-hidden />
              ) : (
                <Pause size={14} strokeWidth={2} aria-hidden />
              )}
            </span>
          </button>
        ) : null}

        <button
          type="button"
          className="main-toolbar-btn run"
          title="运行"
          aria-label="运行"
          onClick={onOpenRun}
        >
          <span className="main-toolbar-icon">
            <Play size={14} strokeWidth={2} aria-hidden />
          </span>
        </button>

        <button
          type="button"
          className={cn("main-toolbar-btn", logOpen && "active")}
          title={logOpen ? "收起底栏" : "展开底栏"}
          aria-label={logOpen ? "收起底栏" : "展开底栏"}
          onClick={onToggleLog}
        >
          <span className="main-toolbar-icon">
            <Terminal size={14} strokeWidth={2} aria-hidden />
          </span>
        </button>
      </div>
    </div>
  );
}
