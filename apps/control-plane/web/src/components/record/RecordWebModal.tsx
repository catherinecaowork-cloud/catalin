import { ChevronDown, ChevronUp, CircleDot } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../../api/client";
import { useRecordContext } from "../../context/RecordContext";
import type { Credential, Site } from "../../types";
import { getRecordUrl, resolveRecordUrl, saveRecordUrl, siteDefaultUrl } from "../../utils/recordUrl";
import { RecordEnvPicker } from "./RecordEnvPicker";
import { RecordEnvironmentsModal } from "./RecordEnvironmentsModal";
import { Alert, Button, Checkbox, Field, Input, Modal, Select } from "../ui";

type Props = {
  open: boolean;
  onClose: () => void;
  sites: Site[];
  selectedSiteId: string | null;
  onSelectSite: (siteId: string) => void;
  onCreateSite: (name: string, baseUrl: string, env?: string) => Promise<unknown>;
  onUpdateSite: (
    siteId: string,
    patch: { name?: string; base_url?: string; env?: string },
  ) => Promise<Site>;
  onDeleteSite: (siteId: string) => Promise<void>;
  onSaveFormLogin: (
    site: Site,
    path: string,
    username: string,
    password: string,
  ) => Promise<void>;
  onDeleteCredential: (siteId: string, credentialId: string) => Promise<void>;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function RecordWebModal({
  open,
  onClose,
  sites,
  selectedSiteId,
  onSelectSite,
  onCreateSite,
  onUpdateSite,
  onDeleteSite,
  onSaveFormLogin,
  onDeleteCredential,
  onLog,
}: Props) {
  const ctx = useRecordContext();
  const [url, setUrl] = useState("");
  const [siteId, setSiteId] = useState<string>("");
  const [credentialId, setCredentialId] = useState("");
  const [intent, setIntent] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [envManageOpen, setEnvManageOpen] = useState(false);

  const refreshCredentials = useCallback(async (targetSiteId: string) => {
    try {
      setCredentials(await api<Credential[]>(`/api/v1/sites/${targetSiteId}/credentials`));
    } catch {
      setCredentials([]);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const initialSiteId = selectedSiteId ?? sites[0]?.id ?? "";
    setSiteId(initialSiteId);
    setCredentialId("");
    setIntent("");
    setMoreOpen(false);
    setError("");
    const initialSite = sites.find((item) => item.id === initialSiteId);
    if (initialSite) {
      setUrl(getRecordUrl(initialSiteId) || siteDefaultUrl(initialSite));
    } else {
      setUrl("");
    }
  }, [open, selectedSiteId, sites]);

  useEffect(() => {
    if (!open || !siteId) {
      setCredentials([]);
      return;
    }
    void refreshCredentials(siteId);
  }, [open, siteId, refreshCredentials]);

  useEffect(() => {
    if (!open || !siteId || envManageOpen) return;
    void refreshCredentials(siteId);
  }, [envManageOpen, open, siteId, refreshCredentials]);

  const applySite = (nextSiteId: string) => {
    setSiteId(nextSiteId);
    onSelectSite(nextSiteId);
    const nextSite = sites.find((item) => item.id === nextSiteId);
    if (nextSite) {
      setUrl(getRecordUrl(nextSiteId) || siteDefaultUrl(nextSite));
    }
    setCredentialId("");
  };

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      if (!siteId) {
        setError("请先选择环境。");
        return;
      }
      if (credentialId && !credentials.some((item) => item.id === credentialId)) {
        setError("所选登录凭证不属于当前环境，请重新选择。");
        return;
      }
      const resolved = resolveRecordUrl(url, sites, siteId);
      if (!resolved) {
        setError("请输入有效的 URL 或路径。");
        return;
      }
      onSelectSite(siteId);
      saveRecordUrl(siteId, resolved.displayUrl);
      await ctx.startRecord({
        siteId,
        startPath: resolved.startPath,
        recordUrl: resolved.displayUrl,
        intent: intent.trim() || `录制 ${resolved.startPath}`,
        credentialId: credentialId || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const closeEnvManage = useCallback(() => {
    setEnvManageOpen(false);
  }, []);

  if (!open) return null;

  return (
    <>
    <Modal
      open
      onClose={onClose}
      className="record-web-modal"
      title={
        <span className="record-web-title">
          <CircleDot size={16} strokeWidth={2} aria-hidden />
          Web 录制
        </span>
      }
      wide
      actions={
        <>
          <Button variant="ghost" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button variant="go" disabled={busy || !url.trim() || !siteId} onClick={() => void start()}>
            录制
          </Button>
        </>
      }
    >
      <div className="record-web-body">
        <div className="record-web-url-bar">
          <label className="record-web-field-label" htmlFor="record-web-url">
            URL
          </label>
          <Input
            id="record-web-url"
            type="text"
            className="record-web-url-input"
            value={url}
            placeholder="http://host:port/ 或 /path"
            onChange={(event) => setUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !busy) void start();
            }}
          />
          <RecordEnvPicker
            sites={sites}
            value={siteId}
            disabled={busy}
            onChange={applySite}
            onManageEnvironments={() => setEnvManageOpen(true)}
          />
        </div>

        <div className="record-web-fields">
          <Field label="登录">
            <Select
              value={credentialId}
              disabled={!siteId || busy}
              onChange={(event) => setCredentialId(event.target.value)}
            >
              <option value="">不登录</option>
              {credentials.map((cred) => (
                <option key={cred.id} value={cred.id}>
                  {cred.name}
                </option>
              ))}
            </Select>
            <p className="record-web-field-note muted">
              仅选择已有凭证；新增或修改请点 URL 旁环境下拉中的 Environments。
            </p>
          </Field>

          <Field label="录制意图">
            <Input
              type="text"
              value={intent}
              placeholder="例如：新增一条款式并确认保存成功"
              disabled={busy}
              onChange={(event) => setIntent(event.target.value)}
            />
          </Field>
        </div>

        <button
          type="button"
          className="record-web-more-toggle"
          onClick={() => setMoreOpen((value) => !value)}
          aria-expanded={moreOpen}
        >
          {moreOpen ? (
            <ChevronUp size={14} strokeWidth={2} aria-hidden />
          ) : (
            <ChevronDown size={14} strokeWidth={2} aria-hidden />
          )}
          <span>更多选项</span>
        </button>

        {moreOpen ? (
          <div className="record-web-more-panel">
            <Checkbox
              label="结束录制后 AI 编译验证"
              checked={ctx.aiCompileEnabled}
              onChange={(event) => ctx.setAiCompileEnabled(event.target.checked)}
            />
          </div>
        ) : null}

        {error ? <Alert variant="error">{error}</Alert> : null}
      </div>
    </Modal>

    <RecordEnvironmentsModal
      open={envManageOpen}
      sites={sites}
      onClose={closeEnvManage}
      onCreateSite={async (name, baseUrl, env) => {
        const created = (await onCreateSite(name, baseUrl, env)) as Site;
        applySite(created.id);
        return created;
      }}
      onUpdateSite={onUpdateSite}
      onDeleteSite={onDeleteSite}
      onSaveFormLogin={onSaveFormLogin}
      onDeleteCredential={onDeleteCredential}
      onLog={onLog}
    />
    </>
  );
}
