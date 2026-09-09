import { useEffect, useState } from "react";

import { Alert, Button, Modal } from "../ui";

type Props = {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "primary" | "danger" | "warn";
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
};

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "确认",
  cancelLabel = "取消",
  variant = "primary",
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) setError("");
  }, [open]);

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
          <Button
            variant={variant}
            disabled={busy}
            onClick={() => {
              setError("");
              void Promise.resolve(onConfirm()).catch((err) =>
                setError(err instanceof Error ? err.message : String(err)),
              );
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="muted">{message}</p>
      {error ? <Alert variant="error">{error}</Alert> : null}
    </Modal>
  );
}
