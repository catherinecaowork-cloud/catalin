import { Activity, Play } from "lucide-react";

import {
  ModuleToolbar,
  ModuleToolbarBadge,
  ModuleToolbarGroup,
  ModuleToolbarLabel,
  ModuleToolbarSpacer,
} from "../patterns/ModuleToolbar";

type Props = {
  title: string;
  color: string;
  badge: string;
};

function badgeTone(badge: string): "ok" | "bad" | "busy" | "muted" {
  const text = badge.toLowerCase();
  if (text.includes("失败") || text.includes("error") || text.includes("离线")) return "bad";
  if (text.includes("运行") || text.includes("等待") || text.includes("排队")) return "busy";
  if (text.includes("通过") || text.includes("在线") || text.includes("完成")) return "ok";
  return "muted";
}

export function RunToolbar({ title, color, badge }: Props) {
  return (
    <ModuleToolbar color={color} className="run-toolbar">
      <ModuleToolbarGroup>
        <ModuleToolbarLabel icon={Play}>{title}</ModuleToolbarLabel>
      </ModuleToolbarGroup>
      <ModuleToolbarSpacer />
      <ModuleToolbarGroup>
        <ModuleToolbarBadge tone={badgeTone(badge)}>
          <Activity size={12} strokeWidth={2} aria-hidden />
          {badge}
        </ModuleToolbarBadge>
      </ModuleToolbarGroup>
    </ModuleToolbar>
  );
}
