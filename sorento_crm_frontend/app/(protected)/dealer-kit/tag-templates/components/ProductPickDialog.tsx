'use client';

/**
 * Pick the product (or set) a block is about.
 *
 * Deliberately NOT `ProductPickerDialog` from the catalogue builder: that one is
 * collection-shaped - it edits pins and exclusions on a rule - while this asks a
 * single question and closes. One search select, server-side, because the
 * catalogue is far past what a client-side filter can see.
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
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import {
  productOptions,
  productSetOptions,
} from '../../services/tagDataService';

export type PickMode = 'product' | 'set';

interface ProductPickDialogProps {
  open: boolean;
  mode: PickMode;
  /** Several at a time, for the alternatives row and the accessories strip. */
  multiple?: boolean;
  title: string;
  confirmLabel?: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (ids: string[]) => void;
}

export function ProductPickDialog({
  open,
  mode,
  multiple = false,
  title,
  confirmLabel = 'Add',
  busy = false,
  onCancel,
  onConfirm,
}: ProductPickDialogProps) {
  const [single, setSingle] = useState('');
  const [many, setMany] = useState<string[]>([]);
  const [selected, setSelected] = useState<SearchableSelectOption[]>([]);

  useEffect(() => {
    if (open) {
      setSingle('');
      setMany([]);
      setSelected([]);
    }
  }, [open]);

  const fetchOptions = useCallback(
    async (query: string) =>
      mode === 'product' ? productOptions(query) : productSetOptions(query),
    [mode],
  );

  const chosen = multiple ? many : single ? [single] : [];

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">
              {mode === 'product' ? 'Product' : 'Product set'}
            </Label>
            {multiple ? (
              <SearchableMultiSelect
                value={many}
                onChange={setMany}
                fetchOptions={fetchOptions}
                selectedOptions={selected}
                placeholder="Search by code or name"
              />
            ) : (
              <SearchableSelect
                value={single}
                onChange={setSingle}
                onOptionChange={(option) => {
                  setSelected(option ? [option] : []);
                }}
                fetchOptions={(query) => fetchOptions(query)}
                selectedOption={selected[0]}
                clearable
                placeholder="Search by code or name"
              />
            )}
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={() => onConfirm(chosen)}
            disabled={busy || chosen.length === 0}
          >
            {busy && <Loader2 className="mr-1 size-3.5 animate-spin" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
