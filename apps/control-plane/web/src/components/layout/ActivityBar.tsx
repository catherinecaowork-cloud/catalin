import { MODULES, type ModuleKind } from "../../types";
import { cn } from "../ui";

import { MODULE_ICONS } from "./moduleIcons";

type Props = {
  activeKind: ModuleKind | null;
  onOpen: (kind: ModuleKind) => void;
};

export function ActivityBar({ activeKind, onOpen }: Props) {
  return (
    <nav className="activity" aria-label="模块">
      {(Object.keys(MODULES) as ModuleKind[]).map((kind) => {
        const Icon = MODULE_ICONS[kind];
        const meta = MODULES[kind];
        const active = activeKind === kind;
        return (
          <button
            key={kind}
            type="button"
            className={cn("act", `kind-${kind}`, active && "active")}
            title={`${meta.title} — ${meta.description}`}
            aria-label={meta.title}
            aria-current={active ? "page" : undefined}
            onClick={() => onOpen(kind)}
          >
            <Icon className="act-icon" aria-hidden strokeWidth={2} size={16} />
          </button>
        );
      })}
    </nav>
  );
}
