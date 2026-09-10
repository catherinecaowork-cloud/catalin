import { useState } from "react";

import type { Credential } from "../../types";
import { Button, Field, IconButton, Input, Muted, SectionTitle } from "../ui";

type Props = {
  selectedSiteId: string | null;
  credentials: Credential[];
  credsLoading: boolean;
  onDeleteCredential: (credentialId: string) => void;
  onSaveLogin: (path: string, username: string, password: string) => Promise<void>;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
  className?: string;
  showTitle?: boolean;
};

export function CredentialForm({
  selectedSiteId,
  credentials,
  credsLoading,
  onDeleteCredential,
  onSaveLogin,
  onLog,
  className = "record-web-section",
  showTitle = true,
}: Props) {
  const [loginPath, setLoginPath] = useState("/");
  const [loginUser, setLoginUser] = useState("");
  const [loginPass, setLoginPass] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <div className={className}>
      {showTitle ? <SectionTitle>当前环境的登录</SectionTitle> : null}
      {!selectedSiteId ? (
        <Muted>选一个站点后再添加账号。</Muted>
      ) : credsLoading ? (
        <Muted>加载凭证…</Muted>
      ) : credentials.length === 0 ? (
        <Muted>还没有登录账号。填下面三项后点识别并保存。</Muted>
      ) : (
        credentials.map((cred) => (
          <div key={cred.id} className="cred-row">
            <span>{cred.name}</span>
            <IconButton
              variant="del"
              title="删除"
              onClick={() => onDeleteCredential(cred.id)}
            >
              ×
            </IconButton>
          </div>
        ))
      )}
      <Field>
        <Input
          type="text"
          value={loginPath}
          placeholder="登录页路径，例如 /login?redirect_url=/"
          onChange={(event) => setLoginPath(event.target.value)}
        />
      </Field>
      <Field>
        <Input
          type="text"
          value={loginUser}
          placeholder="测试账号"
          autoComplete="off"
          onChange={(event) => setLoginUser(event.target.value)}
        />
      </Field>
      <Field>
        <Input
          type="password"
          value={loginPass}
          placeholder="密码"
          autoComplete="off"
          onChange={(event) => setLoginPass(event.target.value)}
        />
      </Field>
      <Button
        variant="primary"
        disabled={!selectedSiteId || busy}
        onClick={() => {
          if (!loginUser.trim() || !loginPass) {
            onLog("账号和密码都要填", "error");
            return;
          }
          setBusy(true);
          void onSaveLogin(loginPath, loginUser.trim(), loginPass)
            .then(() => {
              setLoginPass("");
              onLog("登录凭证已保存");
            })
            .catch((err) => onLog(err instanceof Error ? err.message : String(err), "error"))
            .finally(() => setBusy(false));
        }}
      >
        {busy ? "识别中…" : "识别并保存"}
      </Button>
    </div>
  );
}
