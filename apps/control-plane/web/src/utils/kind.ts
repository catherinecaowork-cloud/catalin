export function kindText(kind: string): string {
  const map: Record<string, string> = {
    record: "录制",
    replay: "回放",
    inspect: "踩点",
  };
  return map[kind] ?? kind ?? "记录";
}

export function compileStatusLabel(
  status: string,
  attempt: number,
  maxAttempts: number,
): string {
  const map: Record<string, string> = {
    queued: "AI 编译排队中",
    compiling: `AI 正在编译（第 ${attempt || 1}/${maxAttempts} 轮）`,
    validating: `正在回放验证（第 ${attempt}/${maxAttempts} 轮）`,
    passed: "AI 编译产物已通过自动回放验证",
    manual_validation: "当前站点不允许自动写入，请人工验证编译结果",
    fallback: "AI 编译未通过，已回退到确定性步骤",
    error: "AI 编译异常",
  };
  return map[status] ?? status;
}
