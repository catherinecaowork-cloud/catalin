import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { AiConfig } from "../types";

export function useAiConfig(onLog: (message: string, level?: "info" | "warn" | "error") => void) {
  const [badge, setBadge] = useState("AI…");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [visionEnabled, setVisionEnabled] = useState(false);
  const [authToken, setAuthToken] = useState("");
  const [tokenPlaceholder, setTokenPlaceholder] = useState("创建密钥时复制的完整 Key");
  const [envHint, setEnvHint] = useState("");

  const refreshBadge = useCallback(async () => {
    try {
      const cfg = await api<AiConfig>("/api/v1/ai/config");
      const ready = cfg.base_url && cfg.model && cfg.has_token;
      setBadge(ready ? "AI 已就绪" : "AI 未配置");
    } catch {
      setBadge("AI 未配置");
    }
  }, []);

  useEffect(() => {
    void refreshBadge();
  }, [refreshBadge]);

  const openModal = useCallback(async () => {
    setOpen(true);
    setError("");
    setSuccess("");
    setAuthToken("");
    setLoading(true);
    try {
      const cfg = await api<AiConfig>("/api/v1/ai/config");
      setBaseUrl(cfg.base_url || "");
      setModel(cfg.model || "");
      setVisionEnabled(!!cfg.vision_enabled);
      setTokenPlaceholder(
        cfg.has_token
          ? `已保存 …${cfg.token_hint ?? ""}，留空不改`
          : "创建密钥时复制的完整 Key",
      );
      const notes: string[] = [];
      if (cfg.api_format && cfg.api_format !== "anthropic") {
        notes.push(`当前模型协议：${cfg.api_format}（不是 Anthropic /v1/messages）`);
      }
      if (cfg.env_overrides?.length) {
        notes.push(
          `本机有环境变量 ${cfg.env_overrides.join("、")}。控制台点保存后以本页为准。`,
        );
      }
      setEnvHint(notes.join(" "));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const save = useCallback(async () => {
    setError("");
    setSuccess("");
    try {
      await api("/api/v1/ai/config", {
        method: "PUT",
        body: JSON.stringify({
          base_url: baseUrl.trim(),
          auth_token: authToken.trim() || null,
          model: model.trim(),
          vision_enabled: visionEnabled,
        }),
      });
      onLog("AI 配置已保存");
      await refreshBadge();
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [baseUrl, authToken, model, visionEnabled, onLog, refreshBadge]);

  const test = useCallback(async () => {
    setError("");
    setSuccess("");
    try {
      if (baseUrl.trim() && model.trim()) {
        await api("/api/v1/ai/config", {
          method: "PUT",
          body: JSON.stringify({
            base_url: baseUrl.trim(),
            auth_token: authToken.trim() || null,
            model: model.trim(),
            vision_enabled: visionEnabled,
          }),
        });
      }
      const result = await api<{ model?: string; preview?: string }>(
        "/api/v1/ai/config/test",
        { method: "POST" },
      );
      onLog(
        `AI 连通正常 · ${result.model ?? ""}${result.preview ? ` · ${result.preview}` : ""}`,
      );
      await refreshBadge();
      setSuccess("连通正常");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [baseUrl, authToken, model, visionEnabled, onLog, refreshBadge]);

  return {
    badge,
    open,
    loading,
    error,
    success,
    baseUrl,
    setBaseUrl,
    model,
    setModel,
    visionEnabled,
    setVisionEnabled,
    authToken,
    setAuthToken,
    tokenPlaceholder,
    envHint,
    openModal,
    closeModal: () => setOpen(false),
    save,
    test,
  };
}
