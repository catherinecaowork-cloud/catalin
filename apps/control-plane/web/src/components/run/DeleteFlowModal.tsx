import { useEffect, useState } from "react";

import { useRunContext } from "../../context/RunContext";
import type { Flow } from "../../types";
import { Alert, Button, Field, Input, Modal } from "../ui";

type Props = {
  flow: Flow | null;
  onClose: () => void;
};

export function DeleteFlowModal({ flow, onClose }: Props) {
  const ctx = useRunContext();
  const [nameInput, setNameInput] = useState("");
  const [confirmInput, setConfirmInput] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!flow) return;
    setNameInput("");
    setConfirmInput("");
    setError("");
  }, [flow]);

  const ok = flow
    ? nameInput.trim() === flow.name && confirmInput.trim() === "delete"
    : false;

  return (
    <Modal
      open={!!flow}
      onClose={onClose}
      title="删除流程"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="danger"
            disabled={!ok || busy}
            onClick={() => {
              if (!flow) return;
              setBusy(true);
              setError("");
              void ctx
                .deleteFlow(flow)
                .then(onClose)
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                .finally(() => setBusy(false));
            }}
          >
            删除流程
          </Button>
        </>
      }
    >
      <p className="muted">此操作不可恢复。运行记录会留下，但无法再跑这条脚本。</p>
      {flow ? (
        <>
          <div className="warn-box">要确认删除，请复制脚本名称，并在下方填入名称和 delete。</div>
          <div className="name-copy">
            <b>{flow.name}</b>
            <Button variant="ghost" onClick={() => void navigator.clipboard.writeText(flow.name)}>
              复制名称
            </Button>
          </div>
        </>
      ) : null}
      <Field label="输入脚本名称">
        <Input
          value={nameInput}
          autoComplete="off"
          onChange={(event) => setNameInput(event.target.value)}
        />
      </Field>
      <Field label="输入 delete">
        <Input
          value={confirmInput}
          placeholder="delete"
          autoComplete="off"
          onChange={(event) => setConfirmInput(event.target.value)}
        />
      </Field>
      {error ? <Alert variant="error">{error}</Alert> : null}
    </Modal>
  );
}
