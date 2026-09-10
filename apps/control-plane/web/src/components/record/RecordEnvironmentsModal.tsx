import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../api/client";
import { useConfirmDialog } from "../../hooks/useConfirmDialog";
import type { Credential, Site } from "../../types";
import { siteEnvBadge, siteEnvLabel, siteEnvTone } from "../../utils/siteEnvDisplay";
import { ConfirmModal } from "../patterns/ConfirmModal";
import { Button, IconButton, Input, Modal, Muted } from "../ui";

const NEW_ENV_ID = "__new__";

type Draft = {
  name: string;
  env: string;
  baseUrl: string;
};

type Props = {
  open: boolean;
  sites: Site[];
  onClose: () => void;
  onCreateSite: (name: string, baseUrl: string, env: string) => Promise<unknown>;
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

function siteDraft(site: Site): Draft {
  return {
    name: site.name.trim() || siteEnvLabel(site),
    env: site.env || "test",
    baseUrl: site.base_url || "",
  };
}

function draftsEqual(left: Draft, right: Draft) {
  return (
    left.name.trim() === right.name.trim() && left.baseUrl.trim() === right.baseUrl.trim()
  );
}

export function RecordEnvironmentsModal({
  open,
  sites,
  onClose,
  onCreateSite,
  onUpdateSite,
  onDeleteSite,
  onSaveFormLogin,
  onDeleteCredential,
  onLog,
}: Props) {
  const { ask, confirmProps } = useConfirmDialog();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({ name: "", env: "test", baseUrl: "" });
  const [savedDraft, setSavedDraft] = useState<Draft>({ name: "", env: "test", baseUrl: "" });
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [credsLoading, setCredsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loginUser, setLoginUser] = useState("");
  const [loginPass, setLoginPass] = useState("");

  const activeSite = useMemo(
    () => (activeId && activeId !== NEW_ENV_ID ? sites.find((site) => site.id === activeId) ?? null : null),
    [activeId, sites],
  );
  const isNew = activeId === NEW_ENV_ID;
  const dirty = !isNew && activeSite ? !draftsEqual(draft, savedDraft) : false;

  const refreshCredentials = useCallback(async (siteId: string) => {
    setCredsLoading(true);
    try {
      setCredentials(await api<Credential[]>(`/api/v1/sites/${siteId}/credentials`));
    } catch {
      setCredentials([]);
    } finally {
      setCredsLoading(false);
    }
  }, []);

  const wasOpen = useRef(false);

  useEffect(() => {
    if (!open) {
      wasOpen.current = false;
      return;
    }
    if (!wasOpen.current) {
      wasOpen.current = true;
      const initialId = sites[0]?.id ?? NEW_ENV_ID;
      setActiveId(initialId);
      if (sites[0]) {
        const next = siteDraft(sites[0]);
        setDraft(next);
        setSavedDraft(next);
      } else {
        setDraft({ name: "", env: "test", baseUrl: "" });
        setSavedDraft({ name: "", env: "test", baseUrl: "" });
      }
      setLoginUser("");
      setLoginPass("");
      return;
    }
    setActiveId((current) => {
      if (current === NEW_ENV_ID) return current;
      if (current && sites.some((site) => site.id === current)) return current;
      const fallback = sites[0]?.id ?? NEW_ENV_ID;
      if (fallback !== NEW_ENV_ID) {
        const site = sites.find((item) => item.id === fallback);
        if (site) {
          const next = siteDraft(site);
          setDraft(next);
          setSavedDraft(next);
        }
      }
      return fallback;
    });
  }, [open, sites]);

  useEffect(() => {
    if (!open || !activeSite) {
      setCredentials([]);
      return;
    }
    void refreshCredentials(activeSite.id);
  }, [open, activeSite, refreshCredentials]);

  const selectSite = (siteId: string) => {
    const site = sites.find((item) => item.id === siteId);
    if (!site) return;
    setActiveId(siteId);
    const next = siteDraft(site);
    setDraft(next);
    setSavedDraft(next);
    setLoginUser("");
    setLoginPass("");
  };

  const startNew = () => {
    setActiveId(NEW_ENV_ID);
    setDraft({ name: "", env: "test", baseUrl: "" });
    setCredentials([]);
    setLoginUser("");
    setLoginPass("");
  };

  const saveSite = async (closeAfter = false) => {
    if (!isNew && activeSite && !dirty) {
      if (closeAfter) onClose();
      return;
    }

    if (isNew) {
      const trimmedName = draft.name.trim();
      const trimmedUrl = draft.baseUrl.trim();
      if (!trimmedName || !trimmedUrl) {
        onLog("请填写环境名称和根地址", "error");
        return;
      }
      setBusy(true);
      try {
        const created = (await onCreateSite(trimmedName, trimmedUrl, draft.env)) as Site;
        const next = siteDraft(created);
        setDraft(next);
        setSavedDraft(next);
        setActiveId(created.id);
        onLog(`已添加环境 ${trimmedName}`);
        if (closeAfter) onClose();
      } catch (err) {
        onLog(err instanceof Error ? err.message : String(err), "error");
      } finally {
        setBusy(false);
      }
      return;
    }

    if (!activeSite) return;
    const trimmedName = draft.name.trim();
    const trimmedUrl = draft.baseUrl.trim();
    if (!trimmedName || !trimmedUrl) {
      onLog("请填写环境名称和根地址", "error");
      return;
    }
    setBusy(true);
    try {
      const updated = await onUpdateSite(activeSite.id, {
        name: trimmedName,
        base_url: trimmedUrl,
      });
      const next = siteDraft(updated);
      setDraft(next);
      setSavedDraft(next);
      onLog(`已保存 ${trimmedName}`);
      if (closeAfter) onClose();
    } catch (err) {
      onLog(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const saveCredential = async () => {
    if (!activeSite) return;
    if (!loginUser.trim() || !loginPass) {
      onLog("账号和密码都要填", "error");
      return;
    }
    setBusy(true);
    try {
      await onSaveFormLogin(activeSite, "/", loginUser.trim(), loginPass);
      setLoginPass("");
      await refreshCredentials(activeSite.id);
      onLog("登录凭证已保存");
    } catch (err) {
      onLog(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <>
      <Modal
        open
        onClose={onClose}
        className="record-env-manage-modal"
        actions={
          <>
            <Button variant="ghost" disabled={busy} onClick={onClose}>
              关闭
            </Button>
            <Button
              variant="primary"
              disabled={busy || (!isNew && !dirty)}
              onClick={() => void saveSite(false)}
            >
              保存
            </Button>
            <Button variant="primary" disabled={busy} onClick={() => void saveSite(true)}>
              保存并关闭
            </Button>
          </>
        }
      >
        <div className="record-env-manage-shell">
          <aside className="record-env-manage-nav">
            <div className="record-env-manage-nav-head">
              <span className="record-env-manage-nav-label">Environments</span>
              <button
                type="button"
                className="record-env-manage-add"
                title="新增环境"
                disabled={busy}
                onClick={startNew}
              >
                <Plus size={14} aria-hidden />
              </button>
            </div>
            <div className="record-env-manage-nav-list" role="listbox" aria-label="环境列表">
              {sites.length === 0 ? (
                <Muted className="record-env-manage-nav-empty">暂无环境</Muted>
              ) : (
                sites.map((site) => {
                  const selected = activeId === site.id;
                  return (
                    <button
                      key={site.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`record-env-manage-nav-item${selected ? " selected" : ""}`}
                      disabled={busy}
                      onClick={() => selectSite(site.id)}
                    >
                      <span className={`record-env-badge tone-${siteEnvTone(site)}`}>
                        {siteEnvBadge(site)}
                      </span>
                      <span className="record-env-manage-nav-name">
                        {site.name.trim() || siteEnvLabel(site)}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </aside>

          <div className="record-env-manage-detail">
            {isNew || activeSite ? (
              <>
                <div className="record-env-manage-detail-head">
                  <div className="record-env-manage-detail-title">
                    {!isNew && activeSite ? (
                      <span className={`record-env-badge tone-${siteEnvTone(activeSite)}`}>
                        {siteEnvBadge(activeSite)}
                      </span>
                    ) : null}
                    <Input
                      type="text"
                      className="record-env-manage-name-input"
                      value={draft.name}
                      placeholder="环境名称"
                      disabled={busy}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, name: event.target.value }))
                      }
                    />
                  </div>
                  {!isNew && activeSite ? (
                    <Button
                      variant="inline"
                      className="record-env-manage-delete"
                      title="删除环境"
                      disabled={busy}
                      onClick={() =>
                        ask({
                          title: "删除环境",
                          message: `删除「${siteEnvLabel(activeSite)}」？相关用例与凭证将不可用于此环境。`,
                          variant: "danger",
                          confirmLabel: "删除",
                          onConfirm: async () => {
                            setBusy(true);
                            try {
                              await onDeleteSite(activeSite.id);
                              onLog(`已删除 ${siteEnvLabel(activeSite)}`);
                              const remaining = sites.filter((site) => site.id !== activeSite.id);
                              if (remaining[0]) selectSite(remaining[0].id);
                              else startNew();
                            } catch (err) {
                              onLog(err instanceof Error ? err.message : String(err), "error");
                            } finally {
                              setBusy(false);
                            }
                          },
                        })
                      }
                    >
                      <Trash2 size={14} aria-hidden />
                    </Button>
                  ) : null}
                </div>

                <section className="record-env-manage-section">
                  <h4 className="record-env-manage-section-title">URL</h4>
                  <Input
                    type="text"
                    value={draft.baseUrl}
                    placeholder="http://host:port"
                    disabled={busy}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, baseUrl: event.target.value }))
                    }
                  />
                </section>

                {!isNew && activeSite ? (
                  <section className="record-env-manage-section">
                    <h4 className="record-env-manage-section-title">凭证</h4>
                    <div className="record-env-manage-vars">
                      <div className="record-env-manage-vars-head">
                        <span>账号</span>
                        <span>密码</span>
                        <span aria-hidden />
                      </div>
                      {credsLoading ? (
                        <p className="muted record-env-manage-vars-empty">加载凭证…</p>
                      ) : credentials.length === 0 ? (
                        <p className="muted record-env-manage-vars-empty">暂无凭证</p>
                      ) : (
                        credentials.map((cred) => (
                          <div key={cred.id} className="record-env-manage-vars-row">
                            <span className="record-env-manage-var-name">{cred.name}</span>
                            <span className="record-env-manage-var-value">••••••</span>
                            <IconButton
                              variant="del"
                              title="删除"
                              disabled={busy}
                              onClick={() =>
                                ask({
                                  title: "删除凭证",
                                  message: `删除「${cred.name}」？`,
                                  variant: "danger",
                                  confirmLabel: "删除",
                                  onConfirm: async () => {
                                    setBusy(true);
                                    try {
                                      await onDeleteCredential(activeSite.id, cred.id);
                                      await refreshCredentials(activeSite.id);
                                      onLog(`已删除凭证 ${cred.name}`);
                                    } catch (err) {
                                      onLog(
                                        err instanceof Error ? err.message : String(err),
                                        "error",
                                      );
                                    } finally {
                                      setBusy(false);
                                    }
                                  },
                                })
                              }
                            >
                              ×
                            </IconButton>
                          </div>
                        ))
                      )}
                      <div className="record-env-manage-vars-add">
                        <Input
                          type="text"
                          value={loginUser}
                          placeholder="账号"
                          autoComplete="off"
                          disabled={busy}
                          onChange={(event) => setLoginUser(event.target.value)}
                        />
                        <Input
                          type="password"
                          value={loginPass}
                          placeholder="密码"
                          autoComplete="off"
                          disabled={busy}
                          onChange={(event) => setLoginPass(event.target.value)}
                        />
                        <Button variant="ghost" disabled={busy} onClick={() => void saveCredential()}>
                          {busy ? "识别中…" : "添加凭证"}
                        </Button>
                      </div>
                    </div>
                  </section>
                ) : null}
              </>
            ) : (
              <div className="record-env-manage-detail-empty">
                <Muted>点击右上角 + 新增环境，或从左侧选择已有环境。</Muted>
              </div>
            )}
          </div>
        </div>
      </Modal>
      <ConfirmModal
        {...confirmProps}
        variant={confirmProps.variant ?? "danger"}
        confirmLabel={confirmProps.confirmLabel ?? "删除"}
      />
    </>
  );
}
