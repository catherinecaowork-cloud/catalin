import { ChevronDown, FolderOpen } from "lucide-react";

import type { Site } from "../../types";
import { cn } from "../ui";

type Props = {
  site: Site | undefined;
  open: boolean;
  onClick: () => void;
};

export function SiteChipTrigger({ site, open, onClick }: Props) {
  return (
    <button
      type="button"
      className={cn("sitechip", open && "open")}
      onClick={onClick}
      title="切换 / 维护站点"
    >
      <FolderOpen className="sitechip-icon" size={14} strokeWidth={2} aria-hidden />
      <span className="label">{site?.name ?? "未选站点"}</span>
      <ChevronDown className="sitechip-caret" size={12} strokeWidth={2} aria-hidden />
    </button>
  );
}
