import type { Site } from "../../types";
import { ExplorerItem } from "../patterns/ExplorerItem";
import { EmptyState } from "../ui";

type Props = {
  sites: Site[];
  selectedSiteId: string | null;
  onSelect: (siteId: string) => void;
  onDelete: (site: Site) => void;
};

export function SiteList({ sites, selectedSiteId, onSelect, onDelete }: Props) {
  if (sites.length === 0) {
    return <EmptyState>还没有站点，在下方添加。</EmptyState>;
  }

  return (
    <>
      {sites.map((site) => (
        <ExplorerItem
          key={site.id}
          selected={site.id === selectedSiteId}
          markColor="var(--c-site)"
          name={site.name}
          sub={site.env}
          onSelect={() => onSelect(site.id)}
          onDelete={() => onDelete(site)}
          deleteTitle="删除站点"
        />
      ))}
    </>
  );
}
