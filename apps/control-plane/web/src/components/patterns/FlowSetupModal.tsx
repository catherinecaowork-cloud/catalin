import { useEffect, useMemo, useState } from "react";

import { useRunContext } from "../../context/RunContext";
import type { Flow } from "../../types";
import { flowSetupIds, flowStatusText } from "../../utils/flow";
import { Alert, Button, EmptyState, Modal, cn } from "../ui";

type Props = {
  flow: Flow | null;
  onClose: () => void;
};

export function FlowSetupModal({ flow, onClose }: Props) {
  const ctx = useRunContext();
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const current = useMemo(
    () => (flow ? ctx.flows.find((item) => item.id === flow.id) ?? flow : null),
    [ctx.flows, flow],
  );

  const candidates = useMemo(
    () => ctx.flows.filter((item) => item.id !== flow?.id),
    [ctx.flows, flow?.id],
  );

  useEffect(() => {
    if (!current) return;
    setPicked(flowSetupIds(current));
    setError("");
  }, [current]);

  if (!flow || !current) return null;

  const toggle = (flowId: string) => {
    setPicked((prev) => {
      if (prev.includes(flowId)) return prev.filter((id) => id !== flowId);
      return [...prev, flowId];
    });
  };

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await ctx.updateSetup(current.id, picked);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const pickedLabels = picked
    .map((id) => ctx.flows.find((item) => item.id === id)?.name)
    .filter(Boolean);

  return (
    <Modal
      open
      onClose={onClose}
      title="前置流程配置"
      wide
      actions={
        <>
          <Button variant="ghost" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" disabled={busy} onClick={() => void save()}>
            保存
          </Button>
        </>
      }
    >
      <div className="setup-modal-intro">
        <div className="setup-modal-target">
          目标用例 <strong>{current.name}</strong>
        </div>
        <p className="setup-modal-hint">勾选前置用例，按勾选顺序依次执行，再跑本条。</p>
      </div>

      {candidates.length === 0 ? (
        <EmptyState>当前站点没有其他用例可选。</EmptyState>
      ) : (
        <div className="setup-modal-list" role="listbox" aria-multiselectable="true">
          {candidates.map((item) => {
            const selected = picked.includes(item.id);
            const order = selected ? picked.indexOf(item.id) + 1 : null;
            return (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn("setup-modal-row", selected && "selected")}
                onClick={() => toggle(item.id)}
              >
                <span className="setup-modal-check" aria-hidden>
                  {order ?? ""}
                </span>
                <span className="setup-modal-name">{item.name}</span>
                <span className={cn("setup-modal-badge", `status-${item.status}`)}>
                  {flowStatusText(item.status)}
                </span>
              </button>
            );
          })}
        </div>
      )}

      <div className="setup-modal-order">
        {pickedLabels.length ? (
          <>
            <span className="setup-modal-order-label">执行顺序</span>
            <span className="setup-modal-order-chain">
              {pickedLabels.join(" → ")} → {current.name}
            </span>
          </>
        ) : (
          <span className="muted">未选前置，将单独跑本条。</span>
        )}
      </div>

      {error ? <Alert variant="error">{error}</Alert> : null}
    </Modal>
  );
}
