'use client';

import { ArrowDown, ArrowUp, GripVertical, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import type { AnyBlockPatch, EmailBlock, EmailBlockType } from '../types/emailTemplate.types';
import { BLOCK_TYPE_LABELS, BLOCK_TYPES, defaultBlockFor, nextBlockId } from '../lib/emailBlocks';
import { BlockSettings } from './blocks/BlockSettings';

export interface BlockListEditorProps {
  blocks: EmailBlock[];
  onChange: (blocks: EmailBlock[]) => void;
}

/**
 * The ordered block list editor (D5, AC-EM040-044): drag to reorder (Sortable
 * from `components/ui/sortable`), explicit Move up/down for anyone who
 * doesn't want to drag, Add from a type menu, Remove, and each block's own
 * settings inline.
 */
export function BlockListEditor({ blocks, onChange }: BlockListEditorProps) {
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= blocks.length) return;
    const next = [...blocks];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  const patchBlock = (id: string, patch: AnyBlockPatch) => {
    onChange(blocks.map((b) => (b.id === id ? ({ ...b, ...patch } as EmailBlock) : b)));
  };

  const removeBlock = (id: string) => {
    onChange(blocks.filter((b) => b.id !== id));
  };

  const addBlock = (type: EmailBlockType) => {
    onChange([...blocks, defaultBlockFor(type, nextBlockId())]);
  };

  return (
    <div className="space-y-3" data-slot="block-list-editor">
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="outline" size="sm">
              <Plus className="mr-1 size-4" /> Add block
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {BLOCK_TYPES.map((type) => (
              <DropdownMenuItem key={type} onSelect={() => addBlock(type)}>
                {BLOCK_TYPE_LABELS[type]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {blocks.length === 0 ? (
        <p className="text-sm text-muted-foreground">No blocks yet. Add one to start building the mail.</p>
      ) : (
        <Sortable
          value={blocks}
          onValueChange={(next) => onChange(next as EmailBlock[])}
          getItemValue={(b) => b.id!}
        >
          <div className="space-y-2">
            {blocks.map((block, index) => (
              <SortableItem key={block.id} value={block.id!} className="rounded-md border bg-card">
                <div className="flex items-start gap-2 p-3">
                  <SortableItemHandle
                    aria-label="Drag to reorder"
                    className="mt-1 shrink-0 text-muted-foreground"
                  >
                    <GripVertical className="size-4" />
                  </SortableItemHandle>
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{BLOCK_TYPE_LABELS[block.type]}</span>
                      <div className="flex shrink-0 items-center gap-0.5">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="size-7 p-0"
                          aria-label="Move up"
                          disabled={index === 0}
                          onClick={() => move(index, -1)}
                        >
                          <ArrowUp className="size-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="size-7 p-0"
                          aria-label="Move down"
                          disabled={index === blocks.length - 1}
                          onClick={() => move(index, 1)}
                        >
                          <ArrowDown className="size-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="size-7 p-0 text-destructive"
                          aria-label="Remove block"
                          onClick={() => removeBlock(block.id!)}
                        >
                          <X className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                    <BlockSettings block={block} onChange={(patch) => patchBlock(block.id!, patch)} />
                  </div>
                </div>
              </SortableItem>
            ))}
          </div>
        </Sortable>
      )}
    </div>
  );
}

export default BlockListEditor;
