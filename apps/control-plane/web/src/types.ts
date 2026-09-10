export type Site = {
  id: string;
  name: string;
  base_url: string;
  env: string;
  adapter: string;
  probe_error_url_patterns: string[];
};

export type PageWidgetEntry = {
  id: string;
  display_name: string;
  widget_kind: string;
  operation: string;
  value_strategy: string;
  choose_mode?: string | null;
  layer?: { kind: string; name?: string | null };
};

export type PageWidgetModel = {
  site_id?: string | null;
  flow_id?: string | null;
  recording_run_id?: string | null;
  entries: PageWidgetEntry[];
  snapshots_seen?: number;
};

export type Flow = {
  id: string;
  site_id: string;
  name: string;
  version: number;
  status: string;
  steps: unknown[];
  auth_type: string;
  has_baseline: boolean;
  setup_flow_id: string | null;
  setup_flow_ids?: string[];
  imported_from: string | null;
  page_widget_model?: PageWidgetModel | null;
};

export type Suite = {
  id: string;
  site_id: string;
  name: string;
  flow_ids: string[];
  created_at: string;
};

export type Batch = {
  id: string;
  site_id: string;
  suite_id: string | null;
  name: string;
  status: string;
  flow_ids: string[];
  current_index: number;
  current_run_id: string | null;
  items: Array<{ flow_id: string; run_id?: string; status?: string }>;
};

export type RunRecord = {
  id: string;
  site_id: string;
  flow_id: string | null;
  kind: string;
  status: string;
  summary: Record<string, unknown> | null;
  duration_seconds: number | null;
  created_at: string;
};

export type RunStep = {
  stepId: string;
  label: string;
  action: string;
  status: string;
  message?: string;
  drift?: string;
  elapsed?: number;
  screenshot?: string;
  /** 命中的定位候选摘要，如 label=PO单号 */
  object?: string;
  /** 填写的值或期望内容 */
  input?: string;
};

export type RunAlert = Record<string, unknown>;
export type RunAssert = Record<string, unknown>;

export type Shot = {
  url: string;
  label: string;
  stepId: string;
};

export type Credential = {
  id: string;
  name: string;
  type: string;
  updated_at: string;
};

export type RecordLiveAction = {
  index: number;
  type: string;
  url?: string | null;
  text?: string | null;
  value?: string | null;
  label?: string | null;
  dialog?: string | null;
  scope?: string | null;
  candidates?: Array<{ kind?: string; value?: string }>;
};

export type RecordStep = {
  id: string;
  action: string;
  phase?: string | null;
  label?: string;
  value?: string;
  expected?: string;
  assert_kind?: string;
  mutating?: boolean;
  target?: Record<string, unknown>;
};

export type RecordingSummary = {
  /** 样例轨迹（Playwright 清洗步骤） */
  sample_steps?: RecordStep[];
  /** 观察者编写脚本；降级时为空 */
  observer_steps?: RecordStep[];
  /** @deprecated 兼容旧 summary，等同 sample_steps */
  steps?: RecordStep[];
  notes?: string[];
  error?: string;
  start_url?: string;
  site_id?: string;
  credential_id?: string | null;
  screenshot?: string | null;
};

export type Compilation = {
  id: string;
  recording_run_id: string;
  status: string;
  attempt: number;
  max_attempts: number;
  steps: RecordStep[];
  sample_steps?: RecordStep[];
  observer_steps?: RecordStep[] | null;
  compile_mode?: "observer" | "polish" | "fallback";
  notes: string[];
  usage?: { input_tokens?: number; output_tokens?: number };
  error?: string | null;
  verified: boolean;
};

export type AiConfig = {
  base_url: string;
  model: string;
  vision_enabled: boolean;
  has_token: boolean;
  token_hint?: string;
  api_format?: string;
  env_overrides?: string[];
};

export type HealPatch = {
  step_id?: string;
  label?: string;
  from_candidate?: string;
  to_candidate?: string;
};

export type HealTask = {
  id: string;
  instruction: string;
  patches: HealPatch[];
  status: string;
};

export type Worker = {
  id: string;
  name: string;
  online: boolean;
  labels: string[];
  platform: string;
};

export type ModuleKind = "site" | "record" | "run" | "history" | "log";

export type EditorTab = {
  id: string;
  kind: ModuleKind;
  title: string;
};

export const MODULES: Record<
  ModuleKind,
  { title: string; color: string; description: string }
> = {
  site: { title: "站点", color: "var(--c-site)", description: "环境与凭证" },
  record: { title: "录制", color: "var(--c-record)", description: "开窗录制 → 保存脚本" },
  run: { title: "运行", color: "var(--c-run)", description: "回放与套件" },
  history: { title: "历史", color: "var(--c-history)", description: "运行记录与产物" },
  log: { title: "日志", color: "var(--c-log)", description: "底栏实时输出" },
};
