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
      <span className="dot" />
      <span className="label">{site?.name ?? "未选站点"}</span>
      <span className="caret">▾</span>
    </button>
  );
}
