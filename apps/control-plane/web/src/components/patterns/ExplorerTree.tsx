import { ChevronDown, ChevronRight, FileText, Folder, Layers, PlayCircle, Search } from "lucide-react";
import { useEffect, useMemo, useState, type MouseEvent, type ReactNode } from "react";

import { cn, EmptyState } from "../ui";

export type ExplorerNodeKind = "folder" | "flow" | "suite" | "run" | "draft" | "site";

export type ExplorerNode = {
  id: string;
  kind: ExplorerNodeKind;
  label: string;
  sub?: string;
  children?: ExplorerNode[];
  selected?: boolean;
  pick?: ReactNode;
  onSelect?: (event?: MouseEvent) => void;
  onContextMenu?: (event: MouseEvent) => void;
  markColor?: string;
  disabled?: boolean;
};

type Props = {
  nodes: ExplorerNode[];
  filter: string;
  onFilterChange: (value: string) => void;
  filterPlaceholder?: string;
  emptyMessage?: string;
  showFilter?: boolean;
  filterActions?: ReactNode;
  onSelectAll?: () => void;
};

function matchesFilter(node: ExplorerNode, filter: string): boolean {
  const q = filter.trim().toLowerCase();
  if (!q) return true;
  const hay = `${node.label} ${node.sub ?? ""}`.toLowerCase();
  return hay.includes(q);
}

function filterExplorerNodes(nodes: ExplorerNode[], filter: string): ExplorerNode[] {
  const q = filter.trim();
  if (!q) return nodes;

  const walk = (items: ExplorerNode[]): ExplorerNode[] => {
    const out: ExplorerNode[] = [];
    for (const node of items) {
      if (node.children) {
        const children = walk(node.children);
        if (children.length || matchesFilter(node, q)) {
          out.push({ ...node, children });
        }
        continue;
      }
      if (matchesFilter(node, q)) out.push(node);
    }
    return out;
  };

  return walk(nodes);
}

function defaultExpandedIds(nodes: ExplorerNode[]): Set<string> {
  const ids = new Set<string>();
  const walk = (items: ExplorerNode[]) => {
    for (const node of items) {
      if (node.children) {
        ids.add(node.id);
        walk(node.children);
      }
    }
  };
  walk(nodes);
  return ids;
}

const LEAF_ICONS: Partial<Record<ExplorerNodeKind, typeof FileText>> = {
  flow: FileText,
  suite: Layers,
  run: PlayCircle,
  draft: FileText,
  site: Folder,
};

function NodeIcon({ kind }: { kind: ExplorerNodeKind }) {
  if (kind === "folder") return <Folder className="tree-icon" size={14} strokeWidth={2} aria-hidden />;
  const Icon = LEAF_ICONS[kind] ?? FileText;
  return <Icon className="tree-icon" size={14} strokeWidth={2} aria-hidden />;
}

function TreeLeaf({ node, depth }: { node: ExplorerNode; depth: number }) {
  return (
    <div
      className={cn(
        "tree-node tree-leaf explorer-item",
        node.selected && "selected",
        node.disabled && "disabled",
      )}
      style={{ paddingLeft: `${8 + depth * 14}px` }}
      onClick={
        node.disabled
          ? undefined
          : (event) => {
              if (event.shiftKey) event.preventDefault();
              node.onSelect?.(event);
            }
      }
      onContextMenu={
        node.onContextMenu
          ? (event) => {
              event.preventDefault();
              node.onContextMenu?.(event);
            }
          : undefined
      }
      onKeyDown={(event) => event.key === "Enter" && !node.disabled && node.onSelect?.()}
      role={node.onSelect ? "button" : undefined}
      tabIndex={node.onSelect && !node.disabled ? 0 : undefined}
    >
      {node.pick}
      <NodeIcon kind={node.kind} />
      {node.markColor ? <span className="mark" style={{ background: node.markColor }} /> : null}
      <span className="name">{node.label}</span>
      {node.sub ? <span className="sub">{node.sub}</span> : null}
    </div>
  );
}

function TreeBranch({
  node,
  depth,
  expandedIds,
  onToggle,
}: {
  node: ExplorerNode;
  depth: number;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  if (node.children) {
    const expanded = expandedIds.has(node.id);
    const count = node.children.length;
    return (
      <div className="tree-folder">
        <div
          className="tree-node tree-folder-head"
          style={{ paddingLeft: `${8 + depth * 14}px` }}
          onClick={() => onToggle(node.id)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onToggle(node.id);
            }
          }}
          role="button"
          tabIndex={0}
          aria-expanded={expanded}
        >
          {node.pick}
          {expanded ? (
            <ChevronDown className="tree-chevron" size={12} strokeWidth={2} aria-hidden />
          ) : (
            <ChevronRight className="tree-chevron" size={12} strokeWidth={2} aria-hidden />
          )}
          <NodeIcon kind="folder" />
          <span className="name">{node.label}</span>
          <span className="sub">{node.sub ?? count}</span>
        </div>
        {expanded ? (
          <div className="tree-children">
            {node.children.map((child) => (
              <TreeBranch
                key={child.id}
                node={child}
                depth={depth + 1}
                expandedIds={expandedIds}
                onToggle={onToggle}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return <TreeLeaf node={node} depth={depth} />;
}

export function ExplorerTree({
  nodes,
  filter,
  onFilterChange,
  filterPlaceholder = "搜索…",
  emptyMessage = "没有匹配项",
  showFilter = true,
  filterActions,
  onSelectAll,
}: Props) {
  const filtered = useMemo(() => filterExplorerNodes(nodes, filter), [nodes, filter]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => defaultExpandedIds(nodes));

  useEffect(() => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      for (const id of defaultExpandedIds(nodes)) next.add(id);
      return next;
    });
  }, [nodes]);

  const toggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div
      className="explorer-tree"
      tabIndex={onSelectAll ? 0 : undefined}
      onKeyDown={(event) => {
        if (!onSelectAll) return;
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
          event.preventDefault();
          onSelectAll();
        }
      }}
    >
      {showFilter ? (
        <div className="explorer-filter">
          <Search className="explorer-filter-icon" size={13} strokeWidth={2} aria-hidden />
          <input
            type="text"
            className="explorer-filter-input"
            value={filter}
            placeholder={filterPlaceholder}
            onChange={(event) => onFilterChange(event.target.value)}
          />
          {filterActions ? <div className="explorer-filter-actions">{filterActions}</div> : null}
        </div>
      ) : null}
      <div className="explorer-tree-body">
        {filtered.length === 0 ? (
          <EmptyState>{emptyMessage}</EmptyState>
        ) : (
          filtered.map((node) => (
            <TreeBranch
              key={node.id}
              node={node}
              depth={0}
              expandedIds={expandedIds}
              onToggle={toggle}
            />
          ))
        )}
      </div>
    </div>
  );
}
