import { useEffect, useRef } from "react";

type Props = {
  x: number;
  y: number;
  onRename?: () => void;
  onConfigureSetup?: () => void;
  onDelete?: () => void;
  deleteLabel?: string;
  onClose: () => void;
};

export function FlowExplorerContextMenu({
  x,
  y,
  onRename,
  onConfigureSetup,
  onDelete,
  deleteLabel = "删除",
  onClose,
}: Props) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  const style = (() => {
    const maxW = 220;
    const pad = 8;
    return {
      top: Math.min(y, window.innerHeight - 200 - pad),
      left: Math.min(x, window.innerWidth - maxW - pad),
    };
  })();

  const hasPrimary = Boolean(onRename || onConfigureSetup);

  return (
    <div ref={menuRef} className="context-menu context-menu-compact" style={style} role="menu">
      {onRename ? (
        <button
          type="button"
          role="menuitem"
          className="context-menu-item"
          onClick={() => {
            onRename();
            onClose();
          }}
        >
          修改名称
        </button>
      ) : null}
      {onConfigureSetup ? (
        <button
          type="button"
          role="menuitem"
          className="context-menu-item"
          onClick={() => {
            onConfigureSetup();
            onClose();
          }}
        >
          前置流程配置
        </button>
      ) : null}
      {onDelete ? (
        <>
          {hasPrimary ? <div className="context-menu-sep" role="separator" /> : null}
          <button
            type="button"
            role="menuitem"
            className="context-menu-item danger"
            onClick={() => {
              onDelete();
              onClose();
            }}
          >
            {deleteLabel}
          </button>
        </>
      ) : null}
    </div>
  );
}
