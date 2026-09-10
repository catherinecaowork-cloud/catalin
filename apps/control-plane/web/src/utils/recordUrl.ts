import type { Site } from "../types";

const URL_KEY = "atp.record.siteUrl";

export function siteDefaultUrl(site: Site): string {
  const base = (site.base_url || "").replace(/\/$/, "");
  return base ? `${base}/` : "";
}

/**
 * 解析录制 URL。站点以用户选择的工作站点为准，不因 URL 同源匹配而切换站点，
 * 避免凭证与 site_id 不一致（多站点共用同一根地址时尤其常见）。
 */
export function resolveRecordUrl(
  input: string,
  sites: Site[],
  preferredSiteId: string | null,
): { siteId: string; startPath: string; displayUrl: string } | null {
  const raw = input.trim();
  if (!raw) return null;

  const site = sites.find((item) => item.id === preferredSiteId) ?? sites[0];
  if (!site) return null;

  if (/^https?:\/\//i.test(raw)) {
    try {
      const parsed = new URL(raw);
      let base: URL | null = null;
      try {
        base = new URL(site.base_url);
      } catch {
        base = null;
      }
      if (base && parsed.origin === base.origin) {
        const startPath = `${parsed.pathname}${parsed.search}${parsed.hash}` || "/";
        return { siteId: site.id, startPath, displayUrl: raw };
      }
      // 跨域或根地址不一致：仍用所选站点，start_path 传完整 URL（执行器支持）
      return { siteId: site.id, startPath: raw, displayUrl: raw };
    } catch {
      return null;
    }
  }

  const startPath = raw.startsWith("/") ? raw : `/${raw}`;
  const base = site.base_url.replace(/\/$/, "");
  return { siteId: site.id, startPath, displayUrl: `${base}${startPath}` };
}

function readAllSiteUrls(): Record<string, string> {
  try {
    const raw = JSON.parse(localStorage.getItem(URL_KEY) || "{}") as Record<string, unknown>;
    const next: Record<string, string> = {};
    for (const [siteId, value] of Object.entries(raw)) {
      if (typeof value === "string" && value.trim()) {
        next[siteId] = value.trim();
        continue;
      }
      if (Array.isArray(value) && typeof value[0] === "string" && value[0].trim()) {
        next[siteId] = value[0].trim();
      }
    }
    return next;
  } catch {
    return {};
  }
}

/** 读取当前环境记住的录制 URL，每个环境仅一条。 */
export function getRecordUrl(siteId: string): string | null {
  const saved = readAllSiteUrls()[siteId];
  return saved ?? null;
}

/** 保存当前环境的录制 URL，覆盖旧值。 */
export function saveRecordUrl(siteId: string, url: string) {
  const trimmed = url.trim();
  if (!trimmed) return;
  try {
    const all = readAllSiteUrls();
    all[siteId] = trimmed;
    localStorage.setItem(URL_KEY, JSON.stringify(all));
  } catch {
    /* ignore quota errors */
  }
}
