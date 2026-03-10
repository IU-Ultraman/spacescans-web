"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { ChevronRight, Loader2 } from "lucide-react";

interface OntologyNode {
  id: string;
  label: string;
  definition: string;
  has_children: boolean;
}

interface TreeNodeState {
  node: OntologyNode;
  children: TreeNodeState[] | null; // null = not loaded
  expanded: boolean;
  loading: boolean;
}

interface OntologyTreeProps {
  selectable?: boolean;
  selected?: string[];
  onSelectionChange?: (ids: string[]) => void;
}

export function OntologyTree({
  selectable = false,
  selected = [],
  onSelectionChange,
}: OntologyTreeProps) {
  const [roots, setRoots] = useState<TreeNodeState[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/ontology/index.json")
      .then((r) => r.json())
      .then((nodes: OntologyNode[]) => {
        setRoots(
          nodes.map((n) => ({
            node: n,
            children: null,
            expanded: false,
            loading: false,
          }))
        );
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const updateNode = useCallback(
    (
      tree: TreeNodeState[],
      targetId: string,
      updater: (n: TreeNodeState) => TreeNodeState
    ): TreeNodeState[] => {
      return tree.map((item) => {
        if (item.node.id === targetId) {
          return updater(item);
        }
        if (item.children) {
          return {
            ...item,
            children: updateNode(item.children, targetId, updater),
          };
        }
        return item;
      });
    },
    []
  );

  const handleToggle = useCallback(
    async (nodeId: string, hasChildren: boolean) => {
      // Find whether it's already expanded
      const findNode = (tree: TreeNodeState[]): TreeNodeState | null => {
        for (const item of tree) {
          if (item.node.id === nodeId) return item;
          if (item.children) {
            const found = findNode(item.children);
            if (found) return found;
          }
        }
        return null;
      };

      const target = findNode(roots);
      if (!target) return;

      if (target.expanded) {
        // Collapse
        setRoots((prev) =>
          updateNode(prev, nodeId, (n) => ({ ...n, expanded: false }))
        );
        return;
      }

      if (!hasChildren) return;

      if (target.children !== null) {
        // Already loaded, just expand
        setRoots((prev) =>
          updateNode(prev, nodeId, (n) => ({ ...n, expanded: true }))
        );
        return;
      }

      // Need to fetch children
      setRoots((prev) =>
        updateNode(prev, nodeId, (n) => ({ ...n, loading: true }))
      );

      try {
        const res = await fetch(`/ontology/nodes/${nodeId}.json`);
        const children: OntologyNode[] = await res.json();
        setRoots((prev) =>
          updateNode(prev, nodeId, (n) => ({
            ...n,
            loading: false,
            expanded: true,
            children: children.map((c) => ({
              node: c,
              children: null,
              expanded: false,
              loading: false,
            })),
          }))
        );
      } catch {
        setRoots((prev) =>
          updateNode(prev, nodeId, (n) => ({ ...n, loading: false }))
        );
      }
    },
    [roots, updateNode]
  );

  const handleCheck = useCallback(
    (id: string, checked: boolean) => {
      if (!onSelectionChange) return;
      if (checked) {
        onSelectionChange([...selected, id]);
      } else {
        onSelectionChange(selected.filter((s) => s !== id));
      }
    },
    [selected, onSelectionChange]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        <Loader2 className="mr-2 size-4 animate-spin" />
        Loading ontology...
      </div>
    );
  }

  return (
    <div className="text-sm">
      {roots.map((item) => (
        <TreeNodeRow
          key={item.node.id}
          item={item}
          depth={0}
          selectable={selectable}
          selected={selected}
          onToggle={handleToggle}
          onCheck={handleCheck}
        />
      ))}
    </div>
  );
}

interface TreeNodeRowProps {
  item: TreeNodeState;
  depth: number;
  selectable: boolean;
  selected: string[];
  onToggle: (id: string, hasChildren: boolean) => void;
  onCheck: (id: string, checked: boolean) => void;
}

function TreeNodeRow({
  item,
  depth,
  selectable,
  selected,
  onToggle,
  onCheck,
}: TreeNodeRowProps) {
  const { node, children, expanded, loading } = item;
  const isSelected = selected.includes(node.id);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1.5 rounded-md px-1.5 py-1 transition-colors hover:bg-muted/60",
          isSelected && "bg-primary/5"
        )}
        style={{ paddingLeft: `${depth * 20 + 6}px` }}
      >
        {/* Expand/collapse chevron */}
        <button
          type="button"
          onClick={() => onToggle(node.id, node.has_children)}
          className={cn(
            "flex size-5 shrink-0 items-center justify-center rounded transition-colors",
            node.has_children
              ? "text-muted-foreground hover:text-foreground"
              : "invisible"
          )}
          tabIndex={node.has_children ? 0 : -1}
        >
          {loading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ChevronRight
              className={cn(
                "size-3.5 transition-transform duration-200",
                expanded && "rotate-90"
              )}
            />
          )}
        </button>

        {/* Checkbox */}
        {selectable && (
          <Checkbox
            checked={isSelected}
            onCheckedChange={(checked) =>
              onCheck(node.id, checked === true)
            }
            className="shrink-0"
          />
        )}

        {/* Label */}
        <button
          type="button"
          onClick={() => {
            if (node.has_children) {
              onToggle(node.id, true);
            } else if (selectable) {
              onCheck(node.id, !isSelected);
            }
          }}
          className="min-w-0 flex-1 truncate text-left text-foreground/90"
          title={node.definition || node.label}
        >
          {node.label.replace(/_/g, " ")}
        </button>
      </div>

      {/* Children */}
      {expanded && children && (
        <div className="animate-in fade-in slide-in-from-top-1 duration-200">
          {children.map((child) => (
            <TreeNodeRow
              key={child.node.id}
              item={child}
              depth={depth + 1}
              selectable={selectable}
              selected={selected}
              onToggle={onToggle}
              onCheck={onCheck}
            />
          ))}
        </div>
      )}
    </div>
  );
}
