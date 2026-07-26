'use client';

import { useEffect, useRef } from 'react';
import { GripVertical, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { Block } from '@/lib/dealer-kit/types';

import { BlockPreview, type ResolvedBinding } from './BlockPreview';
import type { Breakpoint } from '@/lib/dealer-kit/deriveLayout';

/**
 * Block types whose height is decided by their content rather than by the box.
 * These grow the grid item to fit (AC-C4); everything else fills the box it is
 * given.
 */
const FLOWS_TO_CONTENT: ReadonlySet<Block['type']> = new Set(['heading', 'text']);

/**
 * The edit-time frame around a block: selection ring, drag handle, delete.
 *
 * Kept separate from `BlockPreview` because the preview is shared with the
 * public renderer, and none of this chrome may ever reach a reader.
 *
 * It also measures its own content and reports the natural height upward. A
 * block is never allowed to clip what is inside it (AC-C4), and only the DOM
 * knows how tall a heading actually wraps - so the grid learns it by
 * measurement rather than by guessing from the text length.
 */
export function BlockChrome({
  block,
  isSelected,
  onSelect,
  onDelete,
  onMeasure,
  rowSpan,
  resolved,
  breakpoint,
}: {
  block: Block;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onMeasure?: (blockId: string, contentHeightPx: number) => void;
  /** Rows the grid currently allots. Re-reports when it changes so a reflow re-checks fit. */
  rowSpan?: number;
  resolved?: ResolvedBinding;
  breakpoint?: Breakpoint;
}) {
  const headerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || !onMeasure) return;

    const report = () => {
      const header = headerRef.current?.offsetHeight ?? 0;
      // Measure the INNER wrapper, which is laid out at its natural height, not
      // the flex-1 container the grid has already stretched or squashed. The
      // container's scrollHeight is useless here: overflow is visible, so it
      // equals clientHeight even while the text spills past the box.
      onMeasure(block.id, content.offsetHeight + header);
    };

    report();
    const observer = new ResizeObserver(report);
    observer.observe(content);

    return () => observer.disconnect();
    // `rowSpan` and `block.props` are deps on purpose: a ResizeObserver only
    // fires when the observed box itself changes, so after a neighbouring block
    // grows and the grid reflows, nothing would re-check this block's fit.
  }, [block.id, block.props, rowSpan, resolved, onMeasure]);

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
        ref={headerRef}
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

      <div className="min-h-0 flex-1 p-2">
        {/*
          Two kinds of content, measured differently on purpose.

          Text flows: its natural height is the truth, and the block must grow to
          fit it, so the wrapper is left unstretched and measured as-is.

          Images and bound blocks fill whatever box they are given: their natural
          height is meaningless, so they stretch and the Designer sizes them.
        */}
        <div ref={contentRef} className={cn(FLOWS_TO_CONTENT.has(block.type) ? 'h-auto' : 'h-full')}>
          <BlockPreview block={block} resolved={resolved} breakpoint={breakpoint} />
        </div>
      </div>
    </div>
  );
}
