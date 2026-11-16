import { CircleDot, Pause, Play, Square } from "lucide-react";
import { useState } from "react";

import { useRecordContext } from "../../context/RecordContext";
import type { useSites } from "../../hooks/useSites";
import { RecordEnvironmentsModal } from "../record/RecordEnvironmentsModal";
import { RecordEnvPicker } from "../record/RecordEnvPicker";
import { cn } from "../ui";

type SitesState = ReturnType<typeof useSites>;

type Props = {
  sitesState: SitesState;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  onLaunchRecord: () => void;
  onOpenRun: () => void;
};

export function MainToolbar({ sitesState, onLog, onLaunchRecord, onOpenRun }: Props) {
  const record = useRecordContext();
  const recording = record.stage === "busy";
  // 「当前环境」是工作区级状态：explorer / 执行 / 历史 / 录制默认值都跟着它走。
  const [envManageOpen, setEnvManageOpen] = useState(false);

  return (
    <div className="main-toolbar titlebar-toolbar" role="toolbar" aria-label="主操作">
      <div className="main-toolbar-group primary">
        <div className="main-toolbar-env">
          <RecordEnvPicker
            sites={sitesState.sites}
            value={sitesState.selectedSiteId ?? ""}
            onChange={sitesState.setSelectedSiteId}
            onManageEnvironments={() => setEnvManageOpen(true)}
          />
        </div>

        <span className="main-toolbar-sep" aria-hidden />

        <button
          type="button"
          className={cn("main-toolbar-action", "record", recording && "busy")}
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
              <Square size={13} strokeWidth={2} aria-hidden />
            ) : (
              <CircleDot size={14} strokeWidth={2} aria-hidden />
            )}
            {!recording ? <span className="main-toolbar-rec-dot" aria-hidden /> : null}
          </span>
          <span className="main-toolbar-label">{recording ? "结束" : "录制"}</span>
        </button>

        {recording ? (
          <button
            type="button"
            className={cn("main-toolbar-action", "ghost", record.recordPaused && "active")}
            title={record.recordPaused ? "继续录制" : "暂停录制"}
            aria-label={record.recordPaused ? "继续录制" : "暂停录制"}
            onClick={() => void record.toggleRecordPause()}
          >
            <span className="main-toolbar-icon">
              {record.recordPaused ? (
                <Play size={13} strokeWidth={2} aria-hidden />
              ) : (
                <Pause size={13} strokeWidth={2} aria-hidden />
              )}
            </span>
            <span className="main-toolbar-label">{record.recordPaused ? "继续" : "暂停"}</span>
          </button>
        ) : null}

        <button
          type="button"
          className="main-toolbar-action run"
          title="运行"
          aria-label="运行"
          onClick={onOpenRun}
        >
          <span className="main-toolbar-icon">
            <Play size={13} strokeWidth={2} aria-hidden />
          </span>
          <span className="main-toolbar-label">运行</span>
        </button>
      </div>

      <RecordEnvironmentsModal
        open={envManageOpen}
        sites={sitesState.sites}
        onClose={() => setEnvManageOpen(false)}
        onCreateSite={async (name, baseUrl, env) =>
          await sitesState.createSite(name, baseUrl, env)
        }
        onUpdateSite={sitesState.updateSite}
        onDeleteSite={sitesState.deleteSite}
        onSaveFormLogin={(site, path, username, password) =>
          sitesState.saveFormLogin(site, path, username, password, onLog)
        }
        onDeleteCredential={sitesState.deleteCredential}
        onLog={onLog}
      />
    </div>
  );
}
