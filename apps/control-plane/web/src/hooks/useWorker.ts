import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Worker } from "../types";

type StartResult = {
  ok?: boolean;
  already?: boolean;
  pid?: number;
  error?: string;
};

type StopResult = {
  killed?: number[];
  leftover?: number[];
};

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function onlineWorkers(workers: Worker[]) {
  return workers.filter((worker) => worker.online);
}

function workerBadgeText(workers: Worker[], phase: "starting" | "stopping" | null) {
  if (phase === "starting") return "启动中";
  if (phase === "stopping") return "停止中";
  const online = onlineWorkers(workers);
  if (!online.length) return "执行器 0";
  const headed = online.filter((worker) => worker.labels?.includes("headed")).length;
  return `执行器 ${online.length} · 开窗 ${headed}`;
}

export function useWorker(onLog: (line: string) => void) {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<"starting" | "stopping" | null>(null);
  const onLogRef = useRef(onLog);
  onLogRef.current = onLog;

  const refresh = useCallback(async () => {
    try {
      const rows = await api<Worker[]>("/api/v1/workers");
      setWorkers(rows);
      return rows;
    } catch (err) {
      onLogRef.current(
        `Worker 列表失败：${err instanceof Error ? err.message : String(err)}`,
      );
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const online = onlineWorkers(workers).length > 0;
  const badge = workerBadgeText(workers, phase);

  const start = useCallback(async () => {
    setBusy(true);
    setPhase("starting");
    onLogRef.current("正在启动执行器…");
    try {
      const result = await api<StartResult>("/api/v1/workers/local/start", {
        method: "POST",
      });
      if (result.already) {
        onLogRef.current("本机已有执行器进程，等待它上线…");
      } else if (result.pid) {
        onLogRef.current(`已拉起执行器进程 pid=${result.pid}`);
      } else {
        onLogRef.current("已请求启动本地执行器");
      }

      let cameOnline = false;
      for (let i = 0; i < 20; i++) {
        await sleep(500);
        const rows = await refresh();
        if (rows && onlineWorkers(rows).length > 0) {
          cameOnline = true;
          const headed = onlineWorkers(rows).filter((worker) =>
            worker.labels?.includes("headed"),
          ).length;
          onLogRef.current(
            headed
              ? `执行器已上线（开窗 ${headed}）`
              : "执行器已上线",
          );
          break;
        }
      }

      if (!cameOnline) {
        onLogRef.current(
          "进程已拉起但还没上线，看 var/worker-ui.log，或新开终端跑 runner worker",
        );
      }
    } catch (err) {
      onLogRef.current(`启动失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPhase(null);
      setBusy(false);
      await refresh();
    }
  }, [refresh]);

  const stop = useCallback(async () => {
    setBusy(true);
    setPhase("stopping");
    onLogRef.current("正在停止执行器，等待进程退出…");
    try {
      const result = await api<StopResult>("/api/v1/workers/local/stop", {
        method: "POST",
      });
      const leftover = result.leftover ?? [];
      const killed = result.killed ?? [];
      if (leftover.length) {
        onLogRef.current(`停止未完成，仍有进程 ${leftover.join(", ")}`);
      } else {
        onLogRef.current(
          killed.length ? `进程已退出（${killed.length}）` : "没有在跑的本机执行器进程",
        );
      }

      for (let i = 0; i < 20; i++) {
        const rows = await refresh();
        if (rows && !onlineWorkers(rows).length && !leftover.length) {
          onLogRef.current("执行器已停止");
          break;
        }
        if (i === 19 && (onlineWorkers(rows ?? []).length || leftover.length)) {
          onLogRef.current(
            "执行器仍未退出。请看跑 worker 的终端是否还在，或任务管理器里的 python/runner",
          );
        }
        await sleep(500);
      }
    } catch (err) {
      onLogRef.current(`停止失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPhase(null);
      setBusy(false);
      await refresh();
    }
  }, [refresh]);

  return { workers, online, busy, phase, badge, start, stop, refresh };
}
