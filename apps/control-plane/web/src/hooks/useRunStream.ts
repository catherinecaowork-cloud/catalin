import { useCallback, useEffect, useRef, useState } from "react";



import type { Batch, HealTask, RunAlert, RunAssert, RunStep, Shot } from "../types";

import { statusText } from "../utils/flow";
import { parseStepDetail } from "../utils/runStepDisplay";



type RunSummary = {

  status: string;

  summary: Record<string, unknown> | null;

  duration_seconds: number | null;

};



type StreamEvent = {

  seq?: number;

  type: string;

  data?: Record<string, unknown>;

};



const TERMINAL = new Set(["passed", "failed", "error"]);



function stepScreenshot(data: Record<string, unknown>): string | undefined {

  if (data.screenshot) return String(data.screenshot);

  const nested = data.data;

  if (nested && typeof nested === "object" && "screenshot" in nested) {

    const value = (nested as Record<string, unknown>).screenshot;

    return value ? String(value) : undefined;

  }

  return undefined;

}



function buildStepsFromEvents(events: StreamEvent[]): Map<string, RunStep> {

  const steps = new Map<string, RunStep>();

  for (const event of events) {

    const data = event.data ?? {};

    const stepId = String(data.step_id ?? "");

    if (!stepId) continue;

    if (event.type === "step.start") {

      const current = steps.get(stepId);

      steps.set(stepId, {

        stepId,

        label: String(data.label ?? stepId),

        action: String(data.action ?? ""),

        status: "running",

        message: current?.message,

        drift: current?.drift,

        elapsed: current?.elapsed,

        screenshot: current?.screenshot,

      });

    }

    if (event.type === "step.end") {
      const detail = parseStepDetail(data);

      steps.set(stepId, {

        stepId,

        label: String(data.label ?? stepId),

        action: String(data.action ?? ""),

        status: String(data.status ?? "passed"),

        message: data.message ? String(data.message) : undefined,

        drift: data.drift ? String(data.drift) : undefined,

        failure: detail.failure,

        elapsed: typeof data.elapsed_ms === "number" ? data.elapsed_ms : undefined,

        screenshot: stepScreenshot(data),

        object: detail.object,

        input: detail.input,

      });

    }

  }

  return steps;

}



function collectShotsFromEvents(events: StreamEvent[]): Shot[] {

  const shots: Shot[] = [];

  for (const event of events) {

    if (event.type !== "step.end") continue;

    const data = event.data ?? {};

    const url = stepScreenshot(data);

    if (!url) continue;

    const stepId = String(data.step_id ?? "");

    const label = String(data.label ?? "");

    const existing = shots.findIndex((item) => item.url === url);

    if (existing >= 0) {

      shots[existing] = {

        ...shots[existing],

        label: label || shots[existing].label,

        stepId: stepId || shots[existing].stepId,

      };

    } else {

      shots.push({ url, label: label || `第 ${shots.length + 1} 张`, stepId });

    }

  }

  return shots;

}



function appendSummaryShot(

  shots: Shot[],

  summary: Record<string, unknown> | null | undefined,

): Shot[] {

  const url = summary?.screenshot ? String(summary.screenshot) : undefined;

  if (!url || shots.some((item) => item.url === url)) return shots;

  return [...shots, { url, label: "结束画面", stepId: "" }];

}



function hydrateStepsFromSummary(summary: Record<string, unknown> | null): RunStep[] {

  const rows = summary?.steps;

  if (!Array.isArray(rows)) return [];

  return rows.map((row) => {

    const item = row as Record<string, unknown>;

    const stepId = String(item.step_id ?? item.stepId ?? "");

    const detail = parseStepDetail(item);

    return {

      stepId,

      label: String(item.label ?? stepId),

      action: String(item.action ?? ""),

      status: String(item.status ?? "passed"),

      message: item.message ? String(item.message) : undefined,

      drift: item.drift ? String(item.drift) : undefined,

      failure: detail.failure,

      elapsed: typeof item.elapsed_ms === "number" ? item.elapsed_ms : undefined,

      screenshot: item.screenshot ? String(item.screenshot) : undefined,

      object: detail.object,

      input: detail.input,

    };

  });

}



export function useRunStream(

  runId: string | null,

  onLog: (message: string, level?: "info" | "warn" | "error") => void,

  onFollowBatch: (batch: Batch, title: string) => void,

  onRunEnd?: () => void,

) {

  const [runStatus, setRunStatus] = useState<string>("queued");

  const [steps, setSteps] = useState<Map<string, RunStep>>(new Map());

  const [shots, setShots] = useState<Shot[]>([]);

  const [shotIndex, setShotIndex] = useState(0);

  const [alerts, setAlerts] = useState<RunAlert[]>([]);

  const [asserts, setAsserts] = useState<RunAssert[]>([]);

  const [summary, setSummary] = useState<RunSummary | null>(null);

  const [healTask, setHealTask] = useState<HealTask | null>(null);

  const [waitingHint, setWaitingHint] = useState("等待执行器领取任务…");



  const onLogRef = useRef(onLog);

  const onFollowBatchRef = useRef(onFollowBatch);

  const onRunEndRef = useRef(onRunEnd);

  const lastSeqRef = useRef(0);

  onLogRef.current = onLog;

  onFollowBatchRef.current = onFollowBatch;

  onRunEndRef.current = onRunEnd;



  const reset = useCallback(() => {

    setRunStatus("queued");

    setSteps(new Map());

    setShots([]);

    setShotIndex(0);

    setAlerts([]);

    setAsserts([]);

    setSummary(null);

    setHealTask(null);

    setWaitingHint("等待执行器领取任务…");

    lastSeqRef.current = 0;

  }, []);



  useEffect(() => {

    if (!runId) {

      reset();

      return;

    }



    reset();

    onLogRef.current(`订阅 ${runId.slice(0, 8)}`);



    const upsertStep = (stepId: string, patch: Partial<RunStep>) => {

      setSteps((prev) => {

        const next = new Map(prev);

        const current = next.get(stepId) ?? {

          stepId,

          label: stepId,

          action: "",

          status: "queued",

        };

        next.set(stepId, { ...current, ...patch, stepId });

        return next;

      });

    };



    const addShot = (url: string, label: string, stepId: string) => {

      if (!url) return;

      setShots((prev) => {

        const existing = prev.findIndex((item) => item.url === url);

        if (existing >= 0) {

          const copy = [...prev];

          copy[existing] = {

            ...copy[existing],

            label: label || copy[existing].label,

            stepId: stepId || copy[existing].stepId,

          };

          return copy;

        }

        return [...prev, { url, label: label || `第 ${prev.length + 1} 张`, stepId }];

      });

    };



    const rememberSeq = (seq: number | undefined) => {

      if (typeof seq !== "number") return false;

      if (seq <= lastSeqRef.current) return true;

      lastSeqRef.current = seq;

      return false;

    };



    const applyLiveEvent = (event: StreamEvent) => {

      if (rememberSeq(event.seq)) return;



      const data = event.data ?? {};

      if (event.type === "run.start") {

        setSteps(new Map());

        setRunStatus("running");

        onLogRef.current(`开始 ${String(data.flow ?? data.kind ?? "")}`);

        return;

      }

      if (event.type === "step.start") {

        upsertStep(String(data.step_id), {

          label: String(data.label ?? data.step_id),

          action: String(data.action ?? ""),

          status: "running",

        });

        return;

      }

      if (event.type === "step.end") {

        const screenshot = stepScreenshot(data);
        const detail = parseStepDetail(data);

        upsertStep(String(data.step_id), {

          label: String(data.label ?? data.step_id),

          action: String(data.action ?? ""),

          status: String(data.status ?? "passed"),

          message: data.message ? String(data.message) : undefined,

          drift: data.drift ? String(data.drift) : undefined,

          failure: detail.failure,

          elapsed: typeof data.elapsed_ms === "number" ? data.elapsed_ms : undefined,

          screenshot,

          object: detail.object,

          input: detail.input,

        });

        if (screenshot) {

          addShot(screenshot, String(data.label ?? ""), String(data.step_id ?? ""));

        }

        if (data.status === "failed") {

          onLogRef.current(`${data.label} ${data.message ?? ""}`, "error");

        }

        return;

      }

      if (event.type === "probe.alert") {

        setAlerts((prev) => [...prev, data]);

        onLogRef.current(String(data.message ?? data.kind ?? "告警"), "warn");

        return;

      }

      if (event.type === "assert") {

        setAsserts((prev) => [...prev, data]);

        return;

      }

      if (event.type === "log") {

        onLogRef.current(String(data.message ?? ""), data.level === "error" ? "error" : "info");

        if (data.level === "error") {

          setAlerts((prev) => [...prev, { kind: "executor_error", message: data.message }]);

        }

      }

    };



    const applySnapshot = (events: StreamEvent[], runSummary: Record<string, unknown> | null) => {

      const maxSeq = events.reduce((max, item) => Math.max(max, item.seq ?? 0), 0);

      lastSeqRef.current = maxSeq;



      const rebuiltSteps = buildStepsFromEvents(events);

      if (rebuiltSteps.size > 0) {

        setSteps(rebuiltSteps);

      } else {

        const hydrated = hydrateStepsFromSummary(runSummary);

        if (hydrated.length) {

          setSteps(new Map(hydrated.map((step) => [step.stepId, step])));

        }

      }



      setShots(appendSummaryShot(collectShotsFromEvents(events), runSummary));

      setAlerts(events.filter((item) => item.type === "probe.alert").map((item) => item.data ?? {}));

      setAsserts(events.filter((item) => item.type === "assert").map((item) => item.data ?? {}));

    };



    const finishRun = (payload: {

      status: string;

      summary: Record<string, unknown> | null;

      duration_seconds: number | null;

      heal_task: HealTask | null;

      batch?: Batch | null;

    }) => {

      setRunStatus(payload.status);

      setSummary({

        status: payload.status,

        summary: payload.summary,

        duration_seconds: payload.duration_seconds,

      });

      setHealTask(payload.heal_task);

      setShots((prev) => appendSummaryShot(prev, payload.summary));

      onLogRef.current(

        statusText(payload.status),

        payload.status === "passed" ? "info" : "error",

      );



      const batch = payload.batch;

      if (

        batch &&

        batch.status === "running" &&

        batch.current_run_id &&

        batch.current_run_id !== runId

      ) {

        const total = batch.flow_ids?.length ?? 1;

        const n = (batch.current_index ?? 0) + 1;

        const title = total <= 1 ? batch.name : `${batch.name} ${n}/${total}`;

        onFollowBatchRef.current(batch, title);

        return;

      }

      if (batch?.status === "passed") {

        onLogRef.current(`套件「${batch.name}」全部通过`);

      }

      if (batch?.status === "failed") {

        onLogRef.current(`套件「${batch.name}」已停止（失败即停）`, "error");

      }

      onRunEndRef.current?.();

    };



    const source = new EventSource(`/api/v1/runs/${runId}/stream`);



    source.addEventListener("snapshot", (event) => {

      const payload = JSON.parse((event as MessageEvent).data) as {

        run: RunSummary & { summary?: Record<string, unknown> | null };

        events: StreamEvent[];

        heal_task: HealTask | null;

      };

      applySnapshot(payload.events, payload.run.summary ?? null);

      setRunStatus(payload.run.status);

      if (TERMINAL.has(payload.run.status)) {

        setSummary({

          status: payload.run.status,

          summary: payload.run.summary,

          duration_seconds: payload.run.duration_seconds,

        });

        setHealTask(payload.heal_task);

        onRunEndRef.current?.();

        source.close();

      }

    });



    source.addEventListener("event", (event) => {

      applyLiveEvent(JSON.parse((event as MessageEvent).data));

    });



    source.addEventListener("run_end", (event) => {

      const payload = JSON.parse((event as MessageEvent).data) as {

        status: string;

        summary: Record<string, unknown> | null;

        duration_seconds: number | null;

        heal_task: HealTask | null;

        batch: Batch | null;

      };

      finishRun(payload);

      source.close();

    });



    return () => {

      source.close();

    };

  }, [runId, reset]);



  useEffect(() => {

    if (shots.length) setShotIndex(shots.length - 1);

  }, [shots.length]);



  return {

    runStatus,

    steps: [...steps.values()],

    shots,

    shotIndex,

    setShotIndex,

    alerts,

    asserts,

    summary,

    healTask,

    waitingHint,

    setWaitingHint,

    badge: runId ? `${runId.slice(0, 8)} · ${statusText(runStatus)}` : "",

  };

}


