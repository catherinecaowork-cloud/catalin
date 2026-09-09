import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { HealTask } from "../types";
import { Alert, Button, Modal } from "./ui";

type Props = {
  task: HealTask | null;
  onClose: () => void;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function HealModal({ task, onClose, onLog }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [instruction, setInstruction] = useState("");
  const [resultLogs, setResultLogs] = useState<string[]>([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!task) return;
    setError("");
    setDone(false);
    setResultLogs([]);
    const n = task.patches?.length ?? 0;
    setInstruction(
      task.instruction || `监督者要求修改本脚本的 ${n} 处定位。确认后只改这 ${n} 步。`,
    );
    onLog(`AI 监督者：发现 ${n} 处定位漂移，已汇总成修补任务。`, "warn");
  }, [task, onLog]);

  const apply = async () => {
    if (!task) return;
    setBusy(true);
    setError("");
    setInstruction("正在按监督者任务改脚本定位…");
    try {
      const result = await api<{ applied_log?: string[] }>(
        `/api/v1/heal-tasks/${task.id}/apply`,
        { method: "POST" },
      );
      const logs = result.applied_log ?? [];
      const changed = logs.filter((line) => !String(line).startsWith("跳过")).length;
      const summary = changed
        ? `已改 ${changed} 步定位，已写入脚本。`
        : "没有实际改动（步骤可能已不在脚本里）。";
      setInstruction(summary);
      setResultLogs(logs.length ? logs : ["没有返回修改明细"]);
      setDone(true);
      onLog(`AI 执行者：${summary}`);
      logs.forEach((line) => onLog(line));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setInstruction("修改失败，脚本未改。");
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!task) return;
    try {
      await api(`/api/v1/heal-tasks/${task.id}/reject`, { method: "POST" });
      onLog("AI 执行者：用户跳过本次定位修补。");
    } catch (err) {
      onLog(`跳过失败：${err instanceof Error ? err.message : String(err)}`, "error");
    }
    onClose();
  };

  return (
    <Modal
      open={!!task}
      onClose={onClose}
      title="AI 定位修补"
      titleId="healTitle"
      wide
      actions={
        done ? (
          <Button variant="primary" onClick={onClose}>
            关闭
          </Button>
        ) : (
          <>
            <Button variant="ghost" disabled={busy} onClick={() => void reject()}>
              跳过
            </Button>
            <Button variant="primary" disabled={busy} onClick={() => void apply()}>
              {busy ? "修改中…" : "执行修改"}
            </Button>
          </>
        )
      }
    >
      <p className="muted">{instruction}</p>
      {resultLogs.length ? (
        <div className="patch-list">
          {resultLogs.map((line, index) => (
            <div
              key={index}
              className={`patch-item${String(line).startsWith("跳过") ? " skip" : " ok"}`}
            >
              {line}
            </div>
          ))}
        </div>
      ) : (
        <div className="patch-list">
          {(task?.patches ?? []).map((patch, index) => (
            <div key={index} className="patch-item">
              <div>
                {index + 1}. {patch.label || patch.step_id}
              </div>
              <div className="fromto">
                {patch.from_candidate} → <b>{patch.to_candidate}</b>
              </div>
            </div>
          ))}
        </div>
      )}
      {error ? <Alert variant="error">{error}</Alert> : null}
    </Modal>
  );
}
