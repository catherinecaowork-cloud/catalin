import { CircleDot, Clock, Globe, Play, Terminal, type LucideIcon } from "lucide-react";

import type { ModuleKind } from "../../types";

export const MODULE_ICONS: Record<ModuleKind, LucideIcon> = {
  site: Globe,
  record: CircleDot,
  run: Play,
  history: Clock,
  log: Terminal,
};
