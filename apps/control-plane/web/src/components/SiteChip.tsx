import { useEffect, useRef } from "react";

import type { Credential, Site } from "../types";
import { useConfirmDialog } from "../hooks/useConfirmDialog";
import { ConfirmModal } from "./patterns/ConfirmModal";
import { SiteChipTrigger } from "./site/SiteChipTrigger";
import { SiteMenuPanel } from "./site/SiteMenuPanel";

type Props = {
  sites: Site[];
  selectedSiteId: string | null;
  credentials: Credential[];
  credsLoading: boolean;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  onSelect: (siteId: string) => void;
  onRefresh: () => void;
  onCreateSite: (name: string, baseUrl: string) => Promise<unknown>;
  onDeleteSite: (siteId: string) => Promise<void>;
  onDeleteCredential: (credentialId: string) => Promise<void>;
  onSaveLogin: (path: string, username: string, password: string) => Promise<void>;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function SiteChip({
  sites,
  selectedSiteId,
  credentials,
  credsLoading,
  open,
  onToggle,
  onClose,
  onSelect,
  onRefresh,
  onCreateSite,
  onDeleteSite,
  onDeleteCredential,
  onSaveLogin,
  onLog,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const current = sites.find((site) => site.id === selectedSiteId);
  const { ask, confirmProps } = useConfirmDialog();

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) onClose();
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, [open, onClose]);

  const handleOpen = () => {
    if (!open) onRefresh();
    onToggle();
  };

  return (
    <div className="sitechip-wrap" ref={wrapRef}>
      <SiteChipTrigger site={current} open={open} onClick={handleOpen} />
      {open ? (
        <SiteMenuPanel
          sites={sites}
          selectedSiteId={selectedSiteId}
          credentials={credentials}
          credsLoading={credsLoading}
          onSelect={onSelect}
          onDeleteSite={(site) =>
            ask({
              title: "删除站点",
              message: `删除站点「${site.name}」？凭证和流程会一起删。`,
              variant: "danger",
              confirmLabel: "删除",
              onConfirm: () => onDeleteSite(site.id),
            })
          }
          onDeleteCredential={(credentialId) => {
            const cred = credentials.find((item) => item.id === credentialId);
            ask({
              title: "删除登录账号",
              message: `删除登录账号「${cred?.name ?? credentialId}」？`,
              variant: "danger",
              confirmLabel: "删除",
              onConfirm: () => onDeleteCredential(credentialId),
            });
          }}
          onCreateSite={onCreateSite}
          onSaveLogin={onSaveLogin}
          onLog={onLog}
        />
      ) : null}
      <ConfirmModal
        {...confirmProps}
        variant={confirmProps.variant ?? "danger"}
        confirmLabel={confirmProps.confirmLabel ?? "删除"}
      />
    </div>
  );
}
