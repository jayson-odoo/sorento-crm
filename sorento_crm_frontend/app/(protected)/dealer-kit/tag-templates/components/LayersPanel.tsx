'use client';

/**
 * Left sidebar layers panel for the tag canvas editor.
 *
 * Shows all layers sorted by z_index (highest first). Click to select, eye
 * icon for visibility, lock icon for lock state. Layers with `group` type
 * show a disclosure triangle.
 */

import {
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  ImageIcon,
  Lock,
  RectangleHorizontal,
  Shapes,
  Tag,
  Type,
  Unlock,
  Layers,
  DollarSign,
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { TagLayer, TagLayerType } from '@/lib/dealer-kit/tag-template-types';
import { ScrollArea } from '@/components/ui/scroll-area';

function layerIcon(type: TagLayerType) {
  switch (type) {
    case 'text':
      return <Type className="size-3.5" />;
    case 'image':
      return <ImageIcon className="size-3.5" />;
    case 'shape':
      return <Shapes className="size-3.5" />;
    case 'product_slot':
      return <RectangleHorizontal className="size-3.5" />;
    case 'price_field':
      return <DollarSign className="size-3.5" />;
    case 'badge':
      return <Tag className="size-3.5" />;
    case 'group':
      return <Layers className="size-3.5" />;
  }
}

function layerDisplayName(layer: TagLayer): string {
  if (layer.slot_binding) {
    return layer.slot_binding.replace(/_/g, ' ');
  }
  switch (layer.props.kind) {
    case 'text':
      return layer.props.text.slice(0, 24) || 'Text';
    case 'shape':
      return layer.props.shape.replace(/_/g, ' ');
    case 'image':
      return 'Image';
    case 'product_slot':
      return `Slot: ${layer.props.fieldKey}`;
    case 'price_field':
      return `Price (${layer.props.priceType})`;
    case 'badge':
      return 'Badge';
    case 'group':
      return `Group (${layer.props.children.length})`;
  }
}

interface LayersPanelProps {
  layers: TagLayer[];
  selectedIds: Set<string>;
  onSelect: (id: string, additive: boolean) => void;
  onToggleVisibility: (id: string) => void;
  onToggleLock: (id: string) => void;
}

export function LayersPanel({
  layers,
  selectedIds,
  onSelect,
  onToggleVisibility,
  onToggleLock,
}: LayersPanelProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const sorted = [...layers].sort((a, b) => b.z_index - a.z_index);

  // Layers that are children of a group.
  const groupedIds = new Set<string>();
  for (const layer of sorted) {
    if (layer.props.kind === 'group') {
      for (const childId of layer.props.children) {
        groupedIds.add(childId);
      }
    }
  }

  const toggleGroupCollapse = (id: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const renderLayer = (layer: TagLayer, indent = 0) => {
    const isSelected = selectedIds.has(layer.id);
    const isGroup = layer.props.kind === 'group';
    const isCollapsed = collapsedGroups.has(layer.id);

    return (
      <div key={layer.id}>
        <div
          className={cn(
            'flex h-8 cursor-pointer items-center gap-1.5 rounded-sm px-1.5 text-xs hover:bg-accent',
            isSelected && 'bg-accent ring-1 ring-primary/30',
          )}
          style={{ paddingLeft: indent * 16 + 6 }}
          onClick={(e) => onSelect(layer.id, e.shiftKey)}
          role="button"
          tabIndex={0}
        >
          {/* Group collapse toggle */}
          {isGroup ? (
            <button
              type="button"
              className="shrink-0 p-0.5"
              onClick={(e) => {
                e.stopPropagation();
                toggleGroupCollapse(layer.id);
              }}
            >
              {isCollapsed ? (
                <ChevronRight className="size-3" />
              ) : (
                <ChevronDown className="size-3" />
              )}
            </button>
          ) : (
            <span className="w-4" />
          )}

          {/* Type icon */}
          <span className="shrink-0 text-muted-foreground">{layerIcon(layer.type)}</span>

          {/* Name */}
          <span className="min-w-0 flex-1 truncate" title={layerDisplayName(layer)}>
            {layerDisplayName(layer)}
          </span>

          {/* Visibility */}
          <button
            type="button"
            className="shrink-0 p-0.5 text-muted-foreground hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation();
              onToggleVisibility(layer.id);
            }}
            title={layer.visible ? 'Hide layer' : 'Show layer'}
          >
            {layer.visible ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
          </button>

          {/* Lock */}
          <button
            type="button"
            className="shrink-0 p-0.5 text-muted-foreground hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation();
              onToggleLock(layer.id);
            }}
            title={layer.locked ? 'Unlock layer' : 'Lock layer'}
          >
            {layer.locked ? <Lock className="size-3" /> : <Unlock className="size-3" />}
          </button>
        </div>

        {/* Group children */}
        {isGroup && !isCollapsed && (
          <div>
            {(layer.props as { kind: 'group'; children: string[] }).children
              .map((childId) => sorted.find((l) => l.id === childId))
              .filter(Boolean)
              .map((child) => renderLayer(child!, indent + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col border-r">
      <div className="flex h-10 shrink-0 items-center border-b px-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Layers
        </span>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-1">
          {sorted
            .filter((l) => !groupedIds.has(l.id))
            .map((l) => renderLayer(l))}
          {sorted.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-muted-foreground">
              No layers yet
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
