const PHASE_OPTIONS = [
  { value: "", label: "未分组" },
  { value: "setup", label: "前置准备" },
  { value: "main", label: "主流程" },
  { value: "verify", label: "结果校验" },
] as const;

export { PHASE_OPTIONS };
