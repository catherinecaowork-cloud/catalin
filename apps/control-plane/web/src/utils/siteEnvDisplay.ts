import type { Site } from "../types";

const ENV_LABELS: Record<string, string> = {
  dev: "开发环境",
  development: "开发环境",
  test: "测试环境",
  staging: "预发环境",
  prod: "正式环境",
  production: "正式环境",
  local: "本地环境",
  mock: "Mock 环境",
};

const ENV_BADGE: Record<string, string> = {
  dev: "开",
  development: "开",
  test: "测",
  staging: "预",
  prod: "正",
  production: "正",
  local: "本",
  mock: "模",
};

const ENV_TONE: Record<string, string> = {
  dev: "dev",
  development: "dev",
  test: "test",
  staging: "staging",
  prod: "prod",
  production: "prod",
  local: "local",
  mock: "mock",
};

function envKey(site: Site): string {
  return (site.env || "").trim().toLowerCase();
}

export function siteEnvLabel(site: Site): string {
  const name = site.name.trim();
  if (name) return name;
  const key = envKey(site);
  return ENV_LABELS[key] ?? site.env ?? "环境";
}

export function siteEnvBadge(site: Site): string {
  const key = envKey(site);
  if (ENV_BADGE[key]) return ENV_BADGE[key];
  const label = siteEnvLabel(site);
  return label.slice(0, 1) || "?";
}

export function siteEnvTone(site: Site): string {
  const key = envKey(site);
  return ENV_TONE[key] ?? "default";
}
