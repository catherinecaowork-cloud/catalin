import { useEffect, useRef } from "react";

type Props = {
  x: number;
  y: number;
  onConfigureSetup: () => void;
  onClose: () => void;
};

export function FlowExplorerContextMenu({ x, y, onConfigureSetup, onClose }: Props) {
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
      top: Math.min(y, window.innerHeight - 120 - pad),
      left: Math.min(x, window.innerWidth - maxW - pad),
    };
  })();

  return (
    <div ref={menuRef} className="context-menu context-menu-compact" style={style} role="menu">
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
    </div>
  );
}
