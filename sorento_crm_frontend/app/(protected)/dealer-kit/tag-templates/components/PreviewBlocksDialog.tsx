'use client';

/**
 * Choose what each product block on the tag is previewed with (D53).
 *
 * A template with one block asks the single-question `ProductPickDialog`; this
 * is the surface for the ones with several, where "preview with a product" has
 * no single answer. One row per block, each row the same server-searched select
 * `ProductPickDialog` uses, so the sink combo's main sink and its three
 * alternative taps can be looked at as the four different products they are.
 *
 * Nothing here touches the document. Apply hands the choices back and the
 * editor holds them in state until the tab is closed.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { PreviewableBlock } from '@/lib/dealer-kit/preview';
import { productOptions, productSetOptions } from '../../services/tagDataService';

/** What a block is currently previewed with, named the way a person reads it. */
export interface PreviewChoice {
  id: string;
  label: string;
}

interface PreviewBlocksDialogProps {
  open: boolean;
  blocks: PreviewableBlock[];
  /** The choices already in force, so re-opening shows them. */
  value: Record<string, PreviewChoice>;
  busy?: boolean;
  onCancel: () => void;
  onClearAll: () => void;
  onApply: (choices: Record<string, PreviewChoice>) => void;
}

export function PreviewBlocksDialog({
  open,
  blocks,
  value,
  busy = false,
  onCancel,
  onClearAll,
  onApply,
}: PreviewBlocksDialogProps) {
  const [choices, setChoices] = useState<Record<string, PreviewChoice>>({});

  // Re-seeded on every open rather than kept in step: a dialog that opens on
  // stale choices is the drawer bug all over again.
  useEffect(() => {
    if (open) setChoices(value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const pick = useCallback(
    (groupId: string, option: SearchableSelectOption | null) => {
      setChoices((prev) => {
        const next = { ...prev };
        if (!option) delete next[groupId];
        else next[groupId] = { id: String(option.value), label: option.label };
        return next;
      });
    },
    [],
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Preview with products</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-3">
          {blocks.map((block) => (
            <div key={block.groupId} className="flex flex-col gap-1.5">
              <Label className="text-xs text-muted-foreground" title={block.label}>
                {block.label}
              </Label>
              <SearchableSelect
                value={choices[block.groupId]?.id ?? ''}
                onChange={() => {
                  // The option carries the label, so the choice is made in
                  // onOptionChange and this only satisfies the contract.
                }}
                onOptionChange={(option) => pick(block.groupId, option ?? null)}
                fetchOptions={(query) =>
                  block.mode === 'set' ? productSetOptions(query) : productOptions(query)
                }
                selectedOption={
                  choices[block.groupId]
                    ? {
                        value: choices[block.groupId].id,
                        label: choices[block.groupId].label,
                      }
                    : undefined
                }
                clearable
                placeholder={
                  block.mode === 'set'
                    ? 'Search sets by code or name'
                    : 'Search products by code or name'
                }
              />
            </div>
          ))}
        </DialogBody>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={onClearAll}
            disabled={busy || Object.keys(value).length === 0}
          >
            Clear all
          </Button>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => onApply(choices)} disabled={busy}>
            {busy && <Loader2 className="mr-1 size-3.5 animate-spin" />}
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
