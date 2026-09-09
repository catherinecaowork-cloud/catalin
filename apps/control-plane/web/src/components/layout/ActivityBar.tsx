import type { ModuleKind } from "../../types";
import { MODULES } from "../../types";
import { cn } from "../ui";

type Props = {
  activeKind: ModuleKind | null;
  onOpen: (kind: ModuleKind) => void;
};

export function ActivityBar({ activeKind, onOpen }: Props) {
  return (
    <nav className="activity" aria-label="模块">
      {(Object.keys(MODULES) as ModuleKind[]).map((kind) => (
        <button
          key={kind}
          type="button"
          className={cn("act", `kind-${kind}`, activeKind === kind && "active")}
          title={MODULES[kind].description}
          onClick={() => onOpen(kind)}
        >
          {MODULES[kind].title}
        </button>
      ))}
    </nav>
  );
}
