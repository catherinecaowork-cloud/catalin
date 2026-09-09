import { useCallback, useState } from "react";

type ConfirmState = {
  title: string;
  message: string;
  variant?: "primary" | "danger" | "warn";
  confirmLabel?: string;
  onConfirm: () => void | Promise<void>;
};

export function useConfirmDialog() {
  const [state, setState] = useState<ConfirmState | null>(null);

  const ask = useCallback((next: ConfirmState) => {
    setState(next);
  }, []);

  const dismiss = useCallback(() => setState(null), []);

  const confirmProps = {
    open: !!state,
    title: state?.title ?? "",
    message: state?.message ?? "",
    variant: state?.variant,
    confirmLabel: state?.confirmLabel,
    onConfirm: () => {
      const action = state?.onConfirm;
      setState(null);
      return action?.();
    },
    onCancel: dismiss,
  };

  return { ask, dismiss, confirmProps };
}
