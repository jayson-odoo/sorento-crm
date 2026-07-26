'use client';

import { GripVertical, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { Block } from '@/lib/dealer-kit/types';

import { BlockPreview } from './BlockPreview';

/**
 * The edit-time frame around a block: selection ring, drag handle, delete.
 *
 * Kept separate from `BlockPreview` because the preview is shared with the
 * public renderer, and none of this chrome may ever reach a reader.
 */
export function BlockChrome({
  block,
  isSelected,
  onSelect,
  onDelete,
}: {
  block: Block;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        'group relative flex h-full w-full flex-col overflow-hidden rounded-md border bg-card transition-colors',
        isSelected ? 'border-primary ring-1 ring-primary' : 'border-border hover:border-primary/50',
      )}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect();
        }
      }}
      aria-pressed={isSelected}
      aria-label={`${block.type} block`}
    >
      <div
        className={cn(
          'flex shrink-0 items-center gap-1 border-b border-border bg-muted/50 px-1.5 py-1',
          'opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100',
          isSelected && 'opacity-100',
        )}
      >
        <span
          data-dk-drag-handle
          className="flex cursor-grab items-center text-muted-foreground active:cursor-grabbing"
          aria-label="Drag block"
        >
          <GripVertical className="size-3.5" />
        </span>
        <span className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {block.type}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="ms-auto size-6 p-0 text-muted-foreground hover:text-destructive"
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          aria-label={`Delete ${block.type} block`}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-2">
        <BlockPreview block={block} />
      </div>
    </div>
  );
}
