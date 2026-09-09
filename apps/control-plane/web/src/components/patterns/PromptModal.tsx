import { useEffect, useState } from "react";

import { Alert, Button, Field, Input, Modal } from "../ui";

type Props = {
  open: boolean;
  title: string;
  message?: React.ReactNode;
  label?: string;
  defaultValue?: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: (value: string) => void | Promise<void>;
  onCancel: () => void;
};

export function PromptModal({
  open,
  title,
  message,
  label = "名称",
  defaultValue = "",
  placeholder,
  confirmLabel = "确认",
  cancelLabel = "取消",
  onConfirm,
  onCancel,
}: Props) {
  const [value, setValue] = useState(defaultValue);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValue(defaultValue);
    setError("");
    setBusy(false);
  }, [open, defaultValue]);

  const submit = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      setError("请填写内容");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onConfirm(trimmed);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      actions={
        <>
          <Button variant="ghost" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {message ? <p className="muted">{message}</p> : null}
      <Field label={label}>
        <Input
          value={value}
          placeholder={placeholder}
          autoFocus
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void submit();
          }}
        />
      </Field>
      {error ? <Alert variant="error">{error}</Alert> : null}
    </Modal>
  );
}
