import { useCallback, useState } from "react";

export function useLog() {
  const [lines, setLines] = useState<string[]>([]);
  const [open, setOpen] = useState(false);

  const append = useCallback((message: string, level?: "info" | "warn" | "error") => {
    const stamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setLines((prev) => [...prev.slice(-400), `[${stamp}] ${message}`]);
    if (level === "error" || level === "warn") setOpen(true);
  }, []);

  const clear = useCallback(() => setLines([]), []);

  const toggle = useCallback(() => setOpen((value) => !value), []);

  return { lines, open, setOpen, append, clear, toggle };
}
