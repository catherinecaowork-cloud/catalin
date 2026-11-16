import { ChevronDown, Settings } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Site } from "../../types";
import { siteEnvBadge, siteEnvLabel, siteEnvTone } from "../../utils/siteEnvDisplay";

type Props = {
  sites: Site[];
  value: string;
  onChange: (siteId: string) => void;
  onManageEnvironments: () => void;
  disabled?: boolean;
};

export function RecordEnvPicker({
  sites,
  value,
  onChange,
  onManageEnvironments,
  disabled,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = sites.find((item) => item.id === value) ?? null;

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <div className={`record-env-picker${open ? " open" : ""}`} ref={rootRef}>
      <button
        type="button"
        className="record-env-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {selected ? (
          <>
            <span className={`record-env-badge tone-${siteEnvTone(selected)}`}>
              {siteEnvBadge(selected)}
            </span>
            <span className="record-env-name">{siteEnvLabel(selected)}</span>
          </>
        ) : (
          <span className="record-env-name muted">选择环境</span>
        )}
        <ChevronDown size={14} strokeWidth={2} aria-hidden className="record-env-chevron" />
      </button>

      {open ? (
        <div className="record-env-menu">
          <div className="record-env-menu-list" role="listbox">
            {sites.length === 0 ? (
              <p className="record-env-empty muted">暂无环境，点击下方 Environments 添加。</p>
            ) : (
              sites.map((site) => {
                const active = site.id === value;
                return (
                  <button
                    key={site.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={`record-env-option${active ? " active" : ""}`}
                    onClick={() => {
                      onChange(site.id);
                      setOpen(false);
                    }}
                  >
                    <span className={`record-env-badge tone-${siteEnvTone(site)}`}>
                      {siteEnvBadge(site)}
                    </span>
                    <span className="record-env-option-title">{siteEnvLabel(site)}</span>
                  </button>
                );
              })
            )}
          </div>
          <button
            type="button"
            className="record-env-menu-footer"
            onClick={() => {
              setOpen(false);
              onManageEnvironments();
            }}
          >
            <Settings size={14} strokeWidth={2} aria-hidden />
            <span>Environments</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
