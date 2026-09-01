'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';

import { PICKER_PAGE_SIZE, listPickerProducts } from '../../services/productPickerService';
import type { CodeSuggestion } from '../../services/flyerReadingService';
import { useAdoptCode } from '../hooks/useFlyerReadings';
import { printedOn } from './ReportSection';

/**
 * "`SRTBT1835` is which product?" - the one decision an adoption asks for
 * (PLAN-flyer-code-adopt.md, R4: any product, the suggestion is only a
 * default).
 *
 * The picker reaches the WHOLE product master, server-searched and paged
 * (R5) - `SearchableSelect` in `fetchOptions` mode over the same
 * `listPickerProducts` every other Dealer Kit picker uses. A dropdown that
 * loads one page and filters it in the browser has hidden most of a
 * 10,000-plus catalogue before, twice.
 */

export interface AdoptCodeDialogProps {
  readingId: string;
  /** The promotion the report on screen is computed against. See `useAdoptCode`. */
  promotionId?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The printed code this dialog is finding a product for. Null while closed. */
  code: string | null;
  pages: number[];
  suggestion: CodeSuggestion | null;
}

export function AdoptCodeDialog({
  readingId,
  promotionId = null,
  open,
  onOpenChange,
  code,
  pages,
  suggestion,
}: AdoptCodeDialogProps) {
  const [productId, setProductId] = useState('');
  const [selected, setSelected] = useState<SearchableSelectOption | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const adopt = useAdoptCode(readingId, promotionId);

  // Reset to the suggestion (or nothing) every time a different code opens -
  // a choice left over from the last row would be one keystroke away from
  // being recorded against a different printed code.
  useEffect(() => {
    if (!open) return;
    setError(null);
    setProductId(suggestion?.productId ?? '');
    setSelected(
      suggestion
        ? {
            value: suggestion.productId,
            label: suggestion.productCode,
            description: suggestion.productName,
          }
        : undefined,
    );
  }, [open, code, suggestion]);

  const chosenCode = selected && selected.value === productId ? selected.label : null;

  const confirm = () => {
    if (!code || !productId) return;
    setError(null);
    adopt.mutate(
      { printedCode: code, productId },
      {
        onSuccess: () => onOpenChange(false),
        // Stays open on a refusal: the reviewer needs to read it and pick
        // again, most often a different product for R1's "already this one".
        onError: (err) => setError(err.message),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{code ? `${code} is which product?` : 'Which product?'}</DialogTitle>
          {pages.length > 0 && (
            <DialogDescription>Printed on {printedOn(pages)}.</DialogDescription>
          )}
        </DialogHeader>

        <DialogBody className="flex flex-col gap-2">
          <Label htmlFor="dk-fr-adopt-product" className="text-xs">
            Product
          </Label>
          <SearchableSelect
            id="dk-fr-adopt-product"
            value={productId}
            onChange={setProductId}
            onOptionChange={(option) => setSelected(option ?? undefined)}
            // Server-searched and paged over the WHOLE master (R5): never a
            // capped list filtered client-side.
            fetchOptions={async (query, pageIndex) => {
              const rows = await listPickerProducts(query, pageIndex);
              return rows.map((product) => ({
                value: product.id,
                label: product.code,
                description: product.name,
              }));
            }}
            paginated
            pageSize={PICKER_PAGE_SIZE}
            selectedOption={selected}
            clearable
            placeholder="Search by code or name"
          />

          {error && (
            <div
              className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
              data-testid="dk-fr-adopt-error"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <p>{error}</p>
            </div>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            data-testid="dk-fr-adopt-confirm"
            disabled={!productId || adopt.isPending}
            onClick={confirm}
          >
            {adopt.isPending
              ? 'Adopting'
              : chosenCode && code
                ? `Use ${chosenCode} for ${code}`
                : 'Confirm'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
