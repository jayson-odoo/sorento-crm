'use client';

/**
 * Left sidebar layers panel for the tag canvas editor.
 *
 * One FLAT list of rows in panel order (z descending, a group's children
 * indented directly under it), which is what `panelRows` derives. Click to
 * select, eye for visibility, lock for the lock state, and a drag reorders the
 * stack (D43): dropped between two rows a layer takes their place and their
 * parent, dropped onto a group row it joins that group. The rules themselves
 * are pure functions in `canvas-geometry.ts`, so the panel only has to say
 * WHERE the pointer let go.
 */

import {
  Banknote,
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
  Link2Off,
  DollarSign,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type Active,
  type ClientRect,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core';
import { restrictToParentElement, restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { cn } from '@/lib/utils';
import type { TagLayer, TagLayerType } from '@/lib/dealer-kit/tag-template-types';
import { isUnlinked, layerDisplayName } from '@/lib/dealer-kit/product-block';
import {
  panelDropTarget,
  panelRows,
  type ReparentTarget,
} from '@/lib/dealer-kit/canvas-geometry';
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
    case 'price_badge':
      return <Banknote className="size-3.5" />;
    case 'badge':
      return <Tag className="size-3.5" />;
    case 'group':
      return <Layers className="size-3.5" />;
  }
}

/** What a hovered row is about to do with the layer being dragged. */
type DropHint = { overId: string; where: 'above' | 'below' | 'inside' };

/**
 * How far down the hovered row the dragged row sits, 0 at its top edge.
 *
 * Measured from the dragged row's own centre rather than the pointer, because
 * that is what the user is aiming with and what the collision detection already
 * chose the row by.
 */
function hoverRatio(active: Active, overRect: ClientRect): number {
  const dragged = active.rect.current.translated;
  if (!dragged || overRect.height === 0) return 0.5;
  const centre = dragged.top + dragged.height / 2;
  return Math.min(1, Math.max(0, (centre - overRect.top) / overRect.height));
}

interface LayersPanelProps {
  layers: TagLayer[];
  selectedIds: Set<string>;
  onSelect: (id: string, additive: boolean) => void;
  onToggleVisibility: (id: string) => void;
  onToggleLock: (id: string) => void;
  /** Reorder or reparent by drag (D43). */
  onMoveLayer: (id: string, target: ReparentTarget) => void;
}

export function LayersPanel({
  layers,
  selectedIds,
  onSelect,
  onToggleVisibility,
  onToggleLock,
  onMoveLayer,
}: LayersPanelProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [hint, setHint] = useState<DropHint | null>(null);

  const byId = useMemo(
    () => new Map(layers.map((layer) => [layer.id, layer])),
    [layers],
  );

  // Every row, then the ones a collapsed group is hiding taken out. Collapse is
  // panel state, so it survives a drop without anything having to restore it.
  const rows = useMemo(() => {
    const all = panelRows(layers);
    const hidden = new Set<string>();
    return all.filter((row) => {
      if (row.parentId && (hidden.has(row.parentId) || collapsedGroups.has(row.parentId))) {
        hidden.add(row.id);
        return false;
      }
      return true;
    });
  }, [layers, collapsedGroups]);

  const sensors = useSensors(
    // 6px before a drag begins, so a click is still a click and the eye and the
    // lock buttons keep working.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const toggleGroupCollapse = (id: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const intentOf = (
    active: Active,
    overId: string,
    overRect: ClientRect,
  ): { target: ReparentTarget | null; hint: DropHint } => {
    const ratio = hoverRatio(active, overRect);
    const target = panelDropTarget(layers, overId, ratio);
    const where: DropHint['where'] =
      target && target.parentId === overId
        ? 'inside'
        : ratio < 0.5
          ? 'above'
          : 'below';
    return { target, hint: { overId, where } };
  };

  const handleDragOver = ({ active, over }: DragOverEvent) => {
    if (!over || over.id === active.id) {
      setHint(null);
      return;
    }
    setHint(intentOf(active, String(over.id), over.rect).hint);
  };

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    setHint(null);
    if (!over || over.id === active.id) return;
    const { target } = intentOf(active, String(over.id), over.rect);
    if (target) onMoveLayer(String(active.id), target);
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
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            modifiers={[restrictToVerticalAxis, restrictToParentElement]}
            onDragOver={handleDragOver}
            onDragCancel={() => setHint(null)}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={rows.map((row) => row.id)}
              strategy={verticalListSortingStrategy}
            >
              {rows.map((row) => {
                const layer = byId.get(row.id);
                if (!layer) return null;
                return (
                  <LayerRow
                    key={layer.id}
                    layer={layer}
                    depth={row.depth}
                    selected={selectedIds.has(layer.id)}
                    collapsed={collapsedGroups.has(layer.id)}
                    hint={hint?.overId === layer.id ? hint.where : null}
                    onSelect={onSelect}
                    onToggleCollapse={toggleGroupCollapse}
                    onToggleVisibility={onToggleVisibility}
                    onToggleLock={onToggleLock}
                  />
                );
              })}
            </SortableContext>
          </DndContext>
          {rows.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-muted-foreground">
              No layers yet
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function LayerRow({
  layer,
  depth,
  selected,
  collapsed,
  hint,
  onSelect,
  onToggleCollapse,
  onToggleVisibility,
  onToggleLock,
}: {
  layer: TagLayer;
  depth: number;
  selected: boolean;
  collapsed: boolean;
  hint: DropHint['where'] | null;
  onSelect: (id: string, additive: boolean) => void;
  onToggleCollapse: (id: string) => void;
  onToggleVisibility: (id: string) => void;
  onToggleLock: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: layer.id });
  const isGroup = layer.props.kind === 'group';

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'relative',
        isDragging && 'z-10 opacity-60',
        hint === 'above' && 'before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-primary',
        hint === 'below' && 'after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-primary',
      )}
      {...attributes}
      {...listeners}
    >
      <div
        className={cn(
          'flex h-8 cursor-pointer items-center gap-1.5 rounded-sm px-1.5 text-xs hover:bg-accent',
          selected && 'bg-accent ring-1 ring-primary/30',
          hint === 'inside' && 'ring-1 ring-primary',
        )}
        style={{ paddingLeft: depth * 16 + 6 }}
        onClick={(e) => onSelect(layer.id, e.shiftKey)}
        role="button"
        tabIndex={0}
      >
        {/* Group collapse toggle */}
        {isGroup ? (
          <button
            type="button"
            className="shrink-0 p-0.5"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onToggleCollapse(layer.id);
            }}
          >
            {collapsed ? (
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

        {/* Unlinked marker: bound to a slot but showing typed text instead.
            Without it a designer cannot tell which layers stopped following
            the product, which is exactly what they need to know before
            re-binding the block. */}
        {isUnlinked(layer) && (
          <span
            className="shrink-0 text-amber-600"
            title="Unlinked from product data - showing typed text"
          >
            <Link2Off className="size-3" />
          </span>
        )}

        {/* Visibility */}
        <button
          type="button"
          className="shrink-0 p-0.5 text-muted-foreground hover:text-foreground"
          onPointerDown={(e) => e.stopPropagation()}
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
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onToggleLock(layer.id);
          }}
          title={layer.locked ? 'Unlock layer' : 'Lock layer'}
        >
          {layer.locked ? <Lock className="size-3" /> : <Unlock className="size-3" />}
        </button>
      </div>
    </div>
  );
}
