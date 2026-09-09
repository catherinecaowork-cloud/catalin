import { useState } from "react";

import { Button, Field, Input, SectionTitle } from "../ui";

type Props = {
  onCreateSite: (name: string, baseUrl: string) => Promise<unknown>;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function CreateSiteForm({ onCreateSite, onLog }: Props) {
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");

  return (
    <div className="sitemenu-add">
      <SectionTitle>新增站点</SectionTitle>
      <Field>
        <Input
          type="text"
          value={newName}
          placeholder="名称，例如 杰克 MES"
          onChange={(event) => setNewName(event.target.value)}
        />
      </Field>
      <Field>
        <Input
          type="text"
          value={newUrl}
          placeholder="根地址 http://host:port"
          onChange={(event) => setNewUrl(event.target.value)}
        />
      </Field>
      <Button
        variant="primary"
        onClick={() => {
          const name = newName.trim();
          const baseUrl = newUrl.trim();
          if (!name || !baseUrl) {
            onLog("名称和根地址都要填", "error");
            return;
          }
          void onCreateSite(name, baseUrl)
            .then(() => {
              setNewName("");
              setNewUrl("");
              onLog(`已添加 ${name}`);
            })
            .catch((err) => onLog(err instanceof Error ? err.message : String(err), "error"));
        }}
      >
        添加
      </Button>
    </div>
  );
}
