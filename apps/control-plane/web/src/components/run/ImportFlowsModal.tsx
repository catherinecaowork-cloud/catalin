import { useEffect, useState } from "react";

import { api } from "../../api/client";
import { useRunContext } from "../../context/RunContext";
import type { Flow, Site } from "../../types";
import { flowStatusText, otherSites } from "../../utils/flow";
import { ExplorerItem } from "../patterns/ExplorerItem";
import { Alert, Button, EmptyState, Field, Modal, Select } from "../ui";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function ImportFlowsModal({ open, onClose }: Props) {
  const ctx = useRunContext();
  const [sourceSiteId, setSourceSiteId] = useState("");
  const [sourceFlows, setSourceFlows] = useState<Flow[]>([]);
  const [picks, setPicks] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const others = otherSites(ctx.sites, ctx.siteId);

  useEffect(() => {
    if (!open) return;
    setPicks(new Set());
    setError("");
    if (others.length) setSourceSiteId(others[0].id);
  }, [open, others]);

  useEffect(() => {
    if (!open || !sourceSiteId) {
      setSourceFlows([]);
      return;
    }
    void api<Flow[]>(`/api/v1/flows?site_id=${encodeURIComponent(sourceSiteId)}`)
      .then(setSourceFlows)
      .catch((err) => {
        setSourceFlows([]);
        setError(err instanceof Error ? err.message : String(err));
      });
  }, [open, sourceSiteId]);

  const existingNames = new Set(ctx.flows.map((flow) => flow.name));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="从其他环境导入"
      titleId="importFlowsTitle"
      wide
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={busy || others.length === 0}
            onClick={() => {
              const ids = [...picks];
              if (!ids.length) {
                setError("请勾选要导入的脚本");
                return;
              }
              setBusy(true);
              setError("");
              void ctx
                .importFlows(ids)
                .then(() => onClose())
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                .finally(() => setBusy(false));
            }}
          >
            导入到当前环境
          </Button>
        </>
      }
    >
      <p className="muted">
        拷贝到当前环境：地址换成当前站点，登录用当前环境账号。同名已存在则跳过。
      </p>
      {others.length === 0 ? (
        <EmptyState>没有其他环境可导入。先在顶栏添加站点。</EmptyState>
      ) : (
        <>
          <Field label="从哪个环境">
            <Select
              value={sourceSiteId}
              onChange={(event) => setSourceSiteId(event.target.value)}
            >
              {others.map((site: Site) => (
                <option key={site.id} value={site.id}>
                  {site.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="import-list">
            {sourceFlows.length === 0 ? (
              <EmptyState>该环境还没有脚本。</EmptyState>
            ) : (
              sourceFlows.map((flow) => (
                <ExplorerItem
                  key={flow.id}
                  markColor="var(--c-run)"
                  name={flow.name}
                  sub={`${flowStatusText(flow.status)}${existingNames.has(flow.name) ? " · 已有同名" : ""}`}
                  pick={
                    <input
                      type="checkbox"
                      className="pick"
                      checked={picks.has(flow.id)}
                      onChange={(event) => {
                        event.stopPropagation();
                        setPicks((prev) => {
                          const next = new Set(prev);
                          if (event.target.checked) next.add(flow.id);
                          else next.delete(flow.id);
                          return next;
                        });
                      }}
                    />
                  }
                />
              ))
            )}
          </div>
        </>
      )}
      {error ? <Alert variant="error">{error}</Alert> : null}
    </Modal>
  );
}
