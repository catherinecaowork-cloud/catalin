import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { Credential, Site } from "../types";

const SITE_KEY = "atp.siteId";

function siteLoginUrl(site: Site, path: string) {
  const raw = (path || "/").trim() || "/";
  if (/^https?:\/\//i.test(raw)) return raw;
  const base = (site.base_url || "").replace(/\/$/, "");
  return base + (raw.startsWith("/") ? raw : `/${raw}`);
}

async function waitInspect(runId: string, ms = 90000) {
  const started = Date.now();
  while (Date.now() - started < ms) {
    const state = await api<{ status: string }>(`/api/v1/onboarding/inspect/${runId}`);
    if (["passed", "failed", "error"].includes(state.status)) return state;
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error("识别登录表单超时。请确认右上角执行器已点「开始」。");
}

export function useSites() {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteIdState] = useState<string | null>(() =>
    localStorage.getItem(SITE_KEY),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [credsLoading, setCredsLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await api<Site[]>("/api/v1/sites");
      setSites(rows);
      setSelectedSiteIdState((current) => {
        let next = current;
        if (next && !rows.some((site) => site.id === next)) {
          next = rows[0]?.id ?? null;
        }
        if (!next && rows.length) next = rows[0].id;
        if (next) localStorage.setItem(SITE_KEY, next);
        else localStorage.removeItem(SITE_KEY);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshCredentials = useCallback(async (siteId: string | null) => {
    if (!siteId) {
      setCredentials([]);
      return;
    }
    setCredsLoading(true);
    try {
      setCredentials(await api<Credential[]>(`/api/v1/sites/${siteId}/credentials`));
    } catch {
      setCredentials([]);
    } finally {
      setCredsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void refreshCredentials(selectedSiteId);
  }, [selectedSiteId, refreshCredentials]);

  const setSelectedSiteId = useCallback((siteId: string | null) => {
    setSelectedSiteIdState(siteId);
    if (siteId) localStorage.setItem(SITE_KEY, siteId);
    else localStorage.removeItem(SITE_KEY);
  }, []);

  const createSite = useCallback(
    async (name: string, baseUrl: string) => {
      const created = await api<Site>("/api/v1/sites", {
        method: "POST",
        body: JSON.stringify({ name, base_url: baseUrl, env: "test", adapter: "generic" }),
      });
      await refresh();
      setSelectedSiteId(created.id);
      return created;
    },
    [refresh, setSelectedSiteId],
  );

  const deleteSite = useCallback(
    async (siteId: string) => {
      await api(`/api/v1/sites/${siteId}`, { method: "DELETE" });
      if (selectedSiteId === siteId) setSelectedSiteId(null);
      await refresh();
    },
    [selectedSiteId, refresh, setSelectedSiteId],
  );

  const deleteCredential = useCallback(
    async (siteId: string, credentialId: string) => {
      await api(`/api/v1/sites/${siteId}/credentials/${credentialId}`, {
        method: "DELETE",
      });
      await refreshCredentials(siteId);
    },
    [refreshCredentials],
  );

  const saveFormLogin = useCallback(
    async (
      site: Site,
      path: string,
      username: string,
      password: string,
      onLog: (message: string, level?: "info" | "warn" | "error") => void,
    ) => {
      const loginUrl = siteLoginUrl(site, path);
      onLog(`正在打开 ${loginUrl} 识别登录表单`);
      let inspectRunId: string | null = null;
      try {
        const inspect = await api<{ run_id: string }>("/api/v1/onboarding/inspect", {
          method: "POST",
          body: JSON.stringify({ login_url: loginUrl }),
        });
        const state = await waitInspect(inspect.run_id);
        if (state.status === "passed") {
          inspectRunId = inspect.run_id;
        } else {
          onLog("登录页识别失败，改用同项目已有定位", "warn");
        }
      } catch (err) {
        onLog(
          `${err instanceof Error ? err.message : String(err)}；改用同项目已有定位`,
          "warn",
        );
      }
      await api(`/api/v1/sites/${site.id}/credentials/form`, {
        method: "POST",
        body: JSON.stringify({
          name: username,
          username,
          password,
          login_path: path.trim() || "/",
          inspect_run_id: inspectRunId,
        }),
      });
      await refreshCredentials(site.id);
    },
    [refreshCredentials],
  );

  const selectedSite = sites.find((site) => site.id === selectedSiteId) ?? null;

  return {
    sites,
    selectedSite,
    selectedSiteId,
    setSelectedSiteId,
    refresh,
    loading,
    error,
    credentials,
    credsLoading,
    refreshCredentials,
    createSite,
    deleteSite,
    deleteCredential,
    saveFormLogin,
  };
}
