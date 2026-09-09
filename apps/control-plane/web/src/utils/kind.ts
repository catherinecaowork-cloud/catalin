export function kindText(kind: string): string {
  const map: Record<string, string> = {
    record: "录制",
    replay: "回放",
    inspect: "踩点",
  };
  return map[kind] ?? kind ?? "记录";
}

export function compilePathLabel(mode: string | undefined): string {
  const map: Record<string, string> = {
    observer: "观察者编写",
    polish: "仅润色",
    fallback: "样例轨迹（降级）",
  };
  return map[mode ?? ""] ?? "样例轨迹";
}

export function compileStatusLabel(
  status: string,
  attempt: number,
  maxAttempts: number,
  compileMode?: string,
): string {
  const path = compilePathLabel(compileMode);
  const map: Record<string, string> = {
    queued: `${path}排队中`,
    compiling: `${path}中（第 ${attempt || 1}/${maxAttempts} 轮）`,
    validating: `正在无头回放验证（第 ${attempt}/${maxAttempts} 轮）`,
    passed: `${path}已通过自动回放验证`,
    manual_validation: "当前站点不允许自动写入，请人工验证",
    fallback: `${path}未通过，已回退样例轨迹`,
    error: `${path}异常`,
  };
  return map[status] ?? status;
}
