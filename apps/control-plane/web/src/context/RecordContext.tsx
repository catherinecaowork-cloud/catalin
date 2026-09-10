import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api } from "../api/client";
import type {
  Compilation,
  Credential,
  PageWidgetEntry,
  RecordLiveAction,
  RecordStep,
  RecordingSummary,
  Worker,
} from "../types";
import { compilePathLabel, compileStatusLabel } from "../utils/kind";

export type RecordStage = "idle" | "busy" | "result";
export type ScriptSource = "observer" | "sample";

type RecordContextValue = {
  stage: RecordStage;
  recordRunId: string | null;
  intent: string;
  setIntent: (value: string) => void;
  credentialId: string;
  setCredentialId: (value: string) => void;
  startPath: string;
  setStartPath: (value: string) => void;
  aiCompileEnabled: boolean;
  setAiCompileEnabled: (value: boolean) => void;
  credentials: Credential[];
  recordUrl: string;
  eventCount: number;
  recordPaused: boolean;
  liveActions: RecordLiveAction[];
  observedEntries: PageWidgetEntry[];
  scriptSource: ScriptSource;
  sampleSteps: RecordStep[];
  observerSteps: RecordStep[];
  compilePath: string;
  waitingHint: string;
  draftSteps: RecordStep[];
  draftDirty: boolean;
  flowName: string;
  setFlowName: (value: string) => void;
  compilation: Compilation | null;
  compileMessage: string;
  compileError: boolean;
  notes: string[];
  saveHint: string;
  startRecord: (options?: {
    siteId?: string;
    startPath?: string;
    recordUrl?: string;
    intent?: string;
    credentialId?: string | null;
  }) => Promise<void>;
  stopRecord: () => Promise<void>;
  pauseRecord: () => Promise<void>;
  resumeRecord: () => Promise<void>;
  toggleRecordPause: () => Promise<void>;
  retryCompile: () => Promise<void>;
  retryPolishCompile: () => Promise<void>;
  switchScriptSource: (source: ScriptSource) => void;
  useFallbackSteps: () => Promise<void>;
  saveRecord: () => Promise<void>;
  cancelRecord: () => void;
  updateStep: (index: number, patch: Partial<RecordStep>) => void;
  deleteStep: (index: number) => void;
  moveStepUp: (index: number) => void;
  moveStepDown: (index: number) => void;
  addDraftStep: (action?: string, afterIndex?: number) => void;
  setStepUniqueValue: (index: number) => void;
  addAssert: (expected: string) => void;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

const AI_COMPILE_KEY = "atp.record.aiCompile";

const RecordContext = createContext<RecordContextValue | null>(null);

export function useRecordContext() {
  const ctx = useContext(RecordContext);
  if (!ctx) throw new Error("useRecordContext 必须在 RecordProvider 内使用");
  return ctx;
}

type Props = {
  siteId: string | null;
  siteCredentials?: Credential[];
  workers: Worker[];
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  onOpenRecordTab: (runId: string, title: string) => void;
  onRequestAiConfig: () => void;
  children: ReactNode;
};

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function RecordProvider({
  siteId,
  siteCredentials,
  workers,
  onLog,
  onOpenRecordTab,
  onRequestAiConfig,
  children,
}: Props) {
  const [stage, setStage] = useState<RecordStage>("idle");
  const [recordRunId, setRecordRunId] = useState<string | null>(null);
  const [intent, setIntent] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [startPath, setStartPath] = useState("/");
  const [aiCompileEnabled, setAiCompileEnabledState] = useState(
    () => localStorage.getItem(AI_COMPILE_KEY) === "1",
  );
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [recordUrl, setRecordUrl] = useState("");
  const [eventCount, setEventCount] = useState(0);
  const [recordPaused, setRecordPaused] = useState(false);
  const [liveActions, setLiveActions] = useState<RecordLiveAction[]>([]);
  const [observedEntries, setObservedEntries] = useState<PageWidgetEntry[]>([]);
  const [scriptSource, setScriptSource] = useState<ScriptSource>("observer");
  const [sampleSteps, setSampleSteps] = useState<RecordStep[]>([]);
  const [observerSteps, setObserverSteps] = useState<RecordStep[]>([]);
  const [compilePath, setCompilePath] = useState("样例轨迹");
  const [waitingHint, setWaitingHint] = useState("等待执行器领取任务…");
  const [draftSteps, setDraftSteps] = useState<RecordStep[]>([]);
  const [draftDirty, setDraftDirty] = useState(false);
  const [flowName, setFlowName] = useState("");
  const [compilation, setCompilation] = useState<Compilation | null>(null);
  const [compileMessage, setCompileMessage] = useState("");
  const [compileError, setCompileError] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const [saveHint, setSaveHint] = useState("");
  const summaryRef = useRef<RecordingSummary | null>(null);
  const pollTokenRef = useRef(0);

  const headedOnline = workers.some(
    (worker) => worker.online && worker.labels?.includes("headed"),
  );

  const setAiCompileEnabled = useCallback((value: boolean) => {
    setAiCompileEnabledState(value);
    localStorage.setItem(AI_COMPILE_KEY, value ? "1" : "0");
  }, []);

  const updateWaitingHint = useCallback(
    (status?: string) => {
      if (!workers.some((worker) => worker.online)) {
        setWaitingHint("没有在线执行器。请点右上角「开始」。");
        return;
      }
      if (!headedOnline) {
        setWaitingHint("需要带 headed 标签的执行器。请重启 worker。");
        return;
      }
      if (status === "leased") {
        setWaitingHint("执行器已领取，正在启动浏览器…");
      } else if (status === "running") {
        setWaitingHint("看任务栏 Chromium。登录之后再点你要测的流程。");
      } else {
        setWaitingHint("等待执行器领取任务…");
      }
    },
    [workers, headedOnline],
  );

  useEffect(() => {
    if (!siteId) {
      setCredentials([]);
      return;
    }
    if (siteCredentials !== undefined) {
      setCredentials(siteCredentials);
      return;
    }
    void api<Credential[]>(`/api/v1/sites/${siteId}/credentials`)
      .then(setCredentials)
      .catch((err) =>
        onLog(`加载凭证失败：${err instanceof Error ? err.message : String(err)}`, "error"),
      );
  }, [siteId, siteCredentials, onLog]);

  const normalizeSteps = useCallback((rows: RecordStep[]) => {
    return rows.map((step, index) => ({
      ...step,
      id: step.id || `s${index + 1}`,
    }));
  }, []);

  const renderDraft = useCallback(
    (runId: string, summary: RecordingSummary, comp: Compilation | null = null) => {
      const sample = normalizeSteps(
        comp?.sample_steps ?? summary.sample_steps ?? summary.steps ?? [],
      );
      const observer = normalizeSteps(comp?.observer_steps ?? summary.observer_steps ?? []);
      const path = compilePathLabel(comp?.compile_mode);
      const preferObserver =
        Boolean(comp?.verified && observer.length) || (observer.length > 0 && comp?.compile_mode === "observer");
      const nextSource: ScriptSource = preferObserver ? "observer" : "sample";
      const steps = nextSource === "observer" && observer.length ? observer : sample;
      setSampleSteps(sample);
      setObserverSteps(observer);
      setScriptSource(nextSource);
      setCompilePath(path);
      setDraftSteps(steps);
      setDraftDirty(false);
      setNotes([...new Set([...(summary.notes ?? []), ...(comp?.notes ?? [])])]);
      setFlowName(intent.trim());
      setStage("result");
      onOpenRecordTab(runId, "确认步骤");
      onLog(
        `得到 ${steps.length} 步（${path}${comp?.verified ? " · 验证通过" : ""}）`,
      );
    },
    [intent, normalizeSteps, onLog, onOpenRecordTab],
  );

  const pollCompilation = useCallback(
    async (runId: string, token: number) => {
      for (let i = 0; i < 2400; i++) {
        if (pollTokenRef.current !== token) return;
        const state = await api<Compilation>(`/api/v1/recordings/${runId}/compilation`);
        setCompilation(state);
        const label = compileStatusLabel(
          state.status,
          state.attempt,
          state.max_attempts,
          state.compile_mode,
        );
        setCompilePath(compilePathLabel(state.compile_mode));
        const tokenUsage = state.usage?.output_tokens
          ? `（输入 ${state.usage.input_tokens ?? 0} / 输出 ${state.usage.output_tokens} tokens）`
          : "";
        setCompileMessage(label + tokenUsage + (state.error ? `：${state.error}` : ""));
        setCompileError(["fallback", "error"].includes(state.status));

        if (
          ["passed", "manual_validation", "fallback", "error"].includes(state.status)
        ) {
          renderDraft(runId, summaryRef.current ?? {}, state);
          if (
            state.error &&
            /AI 未配置|ai_configuration_missing|缺少配置/.test(state.error)
          ) {
            onRequestAiConfig();
          }
          return;
        }
        await sleep(1000);
      }
    },
    [onRequestAiConfig, renderDraft],
  );

  const beginCompile = useCallback(
    async (summary: RecordingSummary, runId: string, token: number) => {
      summaryRef.current = summary;
      setCompilation(null);
      setDraftDirty(false);
      setStage("result");

      if (!aiCompileEnabled) {
        setCompileMessage("已跳过 AI 编译验证。核对步骤后可保存，需要时再点「重新编译」。");
        setCompileError(false);
        renderDraft(runId, summary, null);
        return;
      }

      onOpenRecordTab(runId, "AI 编译");
      setCompileMessage("正在提交 AI 编译…");
      setCompileError(false);
      try {
        const started = await api<Compilation>(`/api/v1/recordings/${runId}/compile`, {
          method: "POST",
        });
        setCompilation(started);
        await pollCompilation(runId, token);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setCompileMessage(`AI 编译未能启动：${message}`);
        setCompileError(true);
        renderDraft(runId, summary, {
          id: "",
          recording_run_id: runId,
          status: "fallback",
          attempt: 0,
          max_attempts: 3,
          steps: summary.sample_steps ?? summary.steps ?? [],
          notes: [message],
          verified: false,
        });
      }
    },
    [aiCompileEnabled, onOpenRecordTab, pollCompilation, renderDraft],
  );

  const pollRecording = useCallback(
    async (runId: string, token: number) => {
      for (let i = 0; i < 2000; i++) {
        if (pollTokenRef.current !== token) return;
        const state = await api<{
          status: string;
          summary: RecordingSummary;
          paused?: boolean;
          event_count: number;
          live_actions?: RecordLiveAction[];
          observation_model?: { entries?: PageWidgetEntry[] };
          recognized_count?: number;
        }>(`/api/v1/recordings/${runId}`);
        setEventCount(state.event_count ?? 0);
        setRecordPaused(!!state.paused);
        setLiveActions(Array.isArray(state.live_actions) ? state.live_actions : []);
        setObservedEntries(state.observation_model?.entries ?? []);
        updateWaitingHint(state.status);
        if (state.status === "passed") {
          await beginCompile(state.summary ?? {}, runId, token);
          return;
        }
        if (state.status === "failed" || state.status === "error") {
          setStage("idle");
          onLog(state.summary?.error ?? "录制失败", "error");
          return;
        }
        await sleep(1000);
      }
    },
    [beginCompile, onLog, updateWaitingHint],
  );

  const startRecord = useCallback(async (options?: {
    siteId?: string;
    startPath?: string;
    recordUrl?: string;
    intent?: string;
    credentialId?: string | null;
  }) => {
    const effectiveSiteId = options?.siteId ?? siteId;
    const effectiveStartPath = (options?.startPath ?? startPath).trim() || "/";
    const effectiveCredentialId = options?.credentialId ?? credentialId;
    const trimmed = (options?.intent ?? intent).trim() || "Web 录制";
    if (!effectiveSiteId) {
      onLog("请先在高级选项中选择工作站点", "error");
      throw new Error("未选择工作站点");
    }
    setIntent(trimmed);
    setStartPath(effectiveStartPath);
    setCredentialId(effectiveCredentialId || "");
    const token = ++pollTokenRef.current;
    setStage("busy");
    setRecordUrl(
      options?.recordUrl?.trim() ||
        (/^https?:\/\//i.test(effectiveStartPath) ? effectiveStartPath : effectiveStartPath),
    );
    setEventCount(0);
    setRecordPaused(false);
    setLiveActions([]);
    setObservedEntries([]);
    updateWaitingHint("queued");
    onLog("开始录制");
    try {
      const started = await api<{ run_id: string }>("/api/v1/recordings", {
        method: "POST",
        body: JSON.stringify({
          site_id: effectiveSiteId,
          credential_id: effectiveCredentialId || null,
          start_path: effectiveStartPath,
          intent: trimmed,
        }),
      });
      setRecordRunId(started.run_id);
      onOpenRecordTab(started.run_id, "录制中");
      void pollRecording(started.run_id, token);
    } catch (err) {
      setStage("idle");
      const message = err instanceof Error ? err.message : String(err);
      onLog(message, "error");
      throw err instanceof Error ? err : new Error(message);
    }
  }, [
    siteId,
    intent,
    credentialId,
    startPath,
    onLog,
    onOpenRecordTab,
    pollRecording,
    updateWaitingHint,
  ]);

  const stopRecord = useCallback(async () => {
    if (!recordRunId) {
      onLog("当前没有进行中的录制");
      return;
    }
    onLog("正在结束录制…");
    try {
      await api(`/api/v1/recordings/${recordRunId}/stop`, { method: "POST" });
      setRecordPaused(false);
    } catch (err) {
      onLog(err instanceof Error ? err.message : String(err), "error");
    }
  }, [recordRunId, onLog]);

  const pauseRecord = useCallback(async () => {
    if (!recordRunId) return;
    try {
      await api(`/api/v1/recordings/${recordRunId}/pause`, { method: "POST" });
      setRecordPaused(true);
      onLog("录制已暂停");
    } catch (err) {
      onLog(err instanceof Error ? err.message : String(err), "error");
    }
  }, [recordRunId, onLog]);

  const resumeRecord = useCallback(async () => {
    if (!recordRunId) return;
    try {
      await api(`/api/v1/recordings/${recordRunId}/resume`, { method: "POST" });
      setRecordPaused(false);
      onLog("录制已继续");
    } catch (err) {
      onLog(err instanceof Error ? err.message : String(err), "error");
    }
  }, [recordRunId, onLog]);

  const toggleRecordPause = useCallback(async () => {
    if (recordPaused) {
      await resumeRecord();
      return;
    }
    await pauseRecord();
  }, [pauseRecord, recordPaused, resumeRecord]);

  const retryCompileWithMode = useCallback(
    async (compileMode: "observer" | "polish" | null) => {
      if (!recordRunId) return;
      setCompileMessage(compileMode === "polish" ? "正在走润色编译…" : "正在重新编写…");
      setCompileError(false);
      try {
        const next = compilation
          ? await api<Compilation>(`/api/v1/recordings/${recordRunId}/compilation/retry`, {
              method: "POST",
              body: JSON.stringify({
                intent: intent.trim() || null,
                compile_mode: compileMode,
              }),
            })
          : await api<Compilation>(`/api/v1/recordings/${recordRunId}/compile`, {
              method: "POST",
            });
        setCompilation(next);
        await pollCompilation(recordRunId, pollTokenRef.current);
      } catch (err) {
        setCompileMessage(`重新编译失败：${err instanceof Error ? err.message : String(err)}`);
        setCompileError(true);
      }
    },
    [recordRunId, compilation, intent, pollCompilation],
  );

  const retryCompile = useCallback(async () => {
    await retryCompileWithMode("observer");
  }, [retryCompileWithMode]);

  const retryPolishCompile = useCallback(async () => {
    await retryCompileWithMode("polish");
  }, [retryCompileWithMode]);

  const switchScriptSource = useCallback(
    (source: ScriptSource) => {
      setScriptSource(source);
      const rows = source === "observer" ? observerSteps : sampleSteps;
      if (rows.length) {
        setDraftSteps(rows);
        setDraftDirty(false);
      }
    },
    [observerSteps, sampleSteps],
  );

  const useFallbackSteps = useCallback(async () => {
    if (!recordRunId) return;
    try {
      const next = await api<Compilation>(
        `/api/v1/recordings/${recordRunId}/compilation/use-fallback`,
        { method: "POST" },
      );
      setCompilation(next);
      renderDraft(recordRunId, summaryRef.current ?? {}, next);
    } catch (err) {
      setSaveHint(`采用确定性步骤失败：${err instanceof Error ? err.message : String(err)}`);
    }
  }, [recordRunId, renderDraft]);

  const markDirty = useCallback(() => {
    setDraftDirty(true);
    setCompileMessage("步骤已被人工修改，需要重新验证；也可明确选择以 draft 保存");
    setCompileError(false);
  }, []);

  const updateStep = useCallback(
    (index: number, patch: Partial<RecordStep>) => {
      setDraftSteps((prev) =>
        prev.map((step, i) => (i === index ? { ...step, ...patch } : step)),
      );
      markDirty();
    },
    [markDirty],
  );

  const deleteStep = useCallback(
    (index: number) => {
      setDraftSteps((prev) => prev.filter((_, i) => i !== index));
      markDirty();
    },
    [markDirty],
  );

  const moveStep = useCallback(
    (index: number, delta: number) => {
      setDraftSteps((prev) => {
        const nextIndex = index + delta;
        if (index < 0 || index >= prev.length || nextIndex < 0 || nextIndex >= prev.length) {
          return prev;
        }
        const copy = [...prev];
        [copy[index], copy[nextIndex]] = [copy[nextIndex], copy[index]];
        return copy;
      });
      markDirty();
    },
    [markDirty],
  );

  const moveStepUp = useCallback((index: number) => moveStep(index, -1), [moveStep]);
  const moveStepDown = useCallback((index: number) => moveStep(index, 1), [moveStep]);

  const addDraftStep = useCallback(
    (action = "click", afterIndex?: number) => {
      const id = `manual_${Date.now()}`;
      let step: RecordStep;
      switch (action) {
        case "fill":
          step = {
            id,
            action: "fill",
            label: "填写字段",
            value: "",
            target: { candidates: [{ kind: "field", value: "" }] },
            mutating: true,
          };
          break;
        case "choose":
          step = {
            id,
            action: "choose",
            label: "选择选项",
            value: "",
            target: { candidates: [{ kind: "field", value: "" }] },
            mutating: false,
          };
          break;
        case "assert":
          step = {
            id,
            action: "assert",
            assert_kind: "text_contains",
            expected: "",
            label: "断言文本出现",
          };
          break;
        default:
          step = {
            id,
            action: "click",
            label: "点击元素",
            target: { candidates: [{ kind: "text", value: "" }] },
            mutating: false,
          };
      }
      setDraftSteps((prev) => {
        const insertAt =
          afterIndex !== undefined && afterIndex >= 0
            ? Math.min(afterIndex + 1, prev.length)
            : prev.length;
        const copy = [...prev];
        copy.splice(insertAt, 0, step);
        return copy;
      });
      markDirty();
    },
    [markDirty],
  );

  const setStepUniqueValue = useCallback(
    (index: number) => {
      setDraftSteps((prev) =>
        prev.map((step, i) => {
          if (i !== index) return step;
          const key = String(step.id || `value_${index}`).replace(/[^a-zA-Z0-9._-]/g, "_");
          return { ...step, value: `{{unique:${key}}}` };
        }),
      );
      markDirty();
    },
    [markDirty],
  );

  const addAssert = useCallback(
    (expected: string) => {
      const trimmed = expected.trim();
      if (!trimmed) return;
      setDraftSteps((prev) => [
        ...prev,
        {
          id: `assert_${prev.length + 1}`,
          action: "assert",
          assert_kind: "text_contains",
          expected: trimmed,
          label: `断言出现「${trimmed}」`,
        },
      ]);
      markDirty();
    },
    [markDirty],
  );

  const resetRecord = useCallback(() => {
    pollTokenRef.current += 1;
    setStage("idle");
    setRecordRunId(null);
    setDraftSteps([]);
    setDraftDirty(false);
    setCompilation(null);
    setCompileMessage("");
    setNotes([]);
    setSaveHint("");
    setRecordUrl("");
    setEventCount(0);
    setRecordPaused(false);
    setLiveActions([]);
    setObservedEntries([]);
    setSampleSteps([]);
    setObserverSteps([]);
    setScriptSource("observer");
    setCompilePath("样例轨迹");
    summaryRef.current = null;
  }, []);

  const saveRecord = useCallback(async () => {
    if (!recordRunId) {
      setSaveHint("没有可保存的录制。请重新录制，结束后再保存。");
      return;
    }
    if (!draftSteps.length) {
      setSaveHint("没有步骤，不能保存。");
      return;
    }
    const verified = Boolean(compilation?.verified) && !draftDirty;
    let allowUnverified = false;
    if (!verified) {
      allowUnverified = window.confirm("当前步骤未通过自动回放验证。是否仍以 draft 保存？");
      if (!allowUnverified) return;
    }
    const verifiedObserver =
      !draftDirty &&
      Boolean(compilation?.verified) &&
      (compilation?.observer_steps?.length ?? 0) > 0;
    const stepsToSave = verifiedObserver
      ? normalizeSteps(compilation!.observer_steps!)
      : draftSteps;

    setSaveHint("正在保存…");
    try {
      const result = await api<{ flow_id: string; flow_name: string }>(
        `/api/v1/recordings/${recordRunId}/save`,
        {
          method: "POST",
          body: JSON.stringify({
            name: flowName.trim() || "未命名录制",
            steps: stepsToSave,
            allow_unverified: allowUnverified,
          }),
        },
      );
      setSaveHint(`已保存：${result.flow_name}。建议立刻开窗回放验证一次。`);
      onLog(`已保存流程 ${result.flow_name}`);
      resetRecord();
    } catch (err) {
      setSaveHint(`保存失败：${err instanceof Error ? err.message : String(err)}`);
    }
  }, [
    recordRunId,
    draftSteps,
    compilation,
    draftDirty,
    flowName,
    normalizeSteps,
    onLog,
    resetRecord,
  ]);

  const value = useMemo<RecordContextValue>(
    () => ({
      stage,
      recordRunId,
      intent,
      setIntent,
      credentialId,
      setCredentialId,
      startPath,
      setStartPath,
      aiCompileEnabled,
      setAiCompileEnabled,
      credentials,
      recordUrl,
      eventCount,
      recordPaused,
      liveActions,
      observedEntries,
      scriptSource,
      sampleSteps,
      observerSteps,
      compilePath,
      waitingHint,
      draftSteps,
      draftDirty,
      flowName,
      setFlowName,
      compilation,
      compileMessage,
      compileError,
      notes,
      saveHint,
      startRecord,
      stopRecord,
      pauseRecord,
      resumeRecord,
      toggleRecordPause,
      retryCompile,
      retryPolishCompile,
      switchScriptSource,
      useFallbackSteps,
      saveRecord,
      cancelRecord: resetRecord,
      updateStep,
      deleteStep,
      moveStepUp,
      moveStepDown,
      addDraftStep,
      setStepUniqueValue,
      addAssert,
      onLog,
    }),
    [
      stage,
      recordRunId,
      intent,
      credentialId,
      startPath,
      aiCompileEnabled,
      setAiCompileEnabled,
      credentials,
      recordUrl,
      eventCount,
      recordPaused,
      liveActions,
      observedEntries,
      scriptSource,
      sampleSteps,
      observerSteps,
      compilePath,
      waitingHint,
      draftSteps,
      draftDirty,
      flowName,
      compilation,
      compileMessage,
      compileError,
      notes,
      saveHint,
      startRecord,
      stopRecord,
      pauseRecord,
      resumeRecord,
      toggleRecordPause,
      retryCompile,
      retryPolishCompile,
      switchScriptSource,
      useFallbackSteps,
      saveRecord,
      resetRecord,
      updateStep,
      deleteStep,
      moveStepUp,
      moveStepDown,
      addDraftStep,
      setStepUniqueValue,
      addAssert,
      onLog,
    ],
  );

  return <RecordContext.Provider value={value}>{children}</RecordContext.Provider>;
}
