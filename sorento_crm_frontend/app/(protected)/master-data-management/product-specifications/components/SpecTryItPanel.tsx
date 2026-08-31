'use client';

import { Loader2 } from 'lucide-react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Textarea } from '@/components/ui/textarea';
import { fetchProductPickerOptions } from '../services/productSpecService';
import type { TryItSource } from '../hooks/useSpecTryIt';

/**
 * "Try it on" (AC-B.3): pick a real product, or paste text, and see what the DRAFT
 * rules read from it. Sits above the rule list; the per-row reads it drives are
 * rendered INTO those rows (a `readResult` prop on `SpecRuleEditor`), not here - this
 * panel only owns the source and the description it reads from.
 */
export default function SpecTryItPanel({
  source,
  onSourceChange,
  description,
  loading,
  error,
}: {
  source: TryItSource | null;
  onSourceChange: (source: TryItSource | null) => void;
  description: string | null;
  loading: boolean;
  error: string | null;
}) {
  const pastedText = source?.type === 'text' ? source.text : '';

  return (
    <div className="flex flex-col gap-2 rounded-md border bg-muted/10 p-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        Try it on
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="min-w-[16rem] flex-1">
          <SearchableSelect
            value={source?.type === 'product' ? source.productId : ''}
            onChange={() => {}}
            onOptionChange={(opt) =>
              onSourceChange(
                opt
                  ? {
                      type: 'product',
                      productId: opt.value,
                      productLabel: opt.label,
                    }
                  : null,
              )
            }
            fetchOptions={fetchProductPickerOptions}
            paginated
            pageSize={50}
            clearable
            placeholder="Search the product master..."
            emptyMessage="No products found."
          />
        </div>
        <span className="pt-2 text-xs text-muted-foreground sm:pt-0">or</span>
        <Textarea
          variant="sm"
          className="min-h-[2.25rem] min-w-[16rem] flex-1"
          placeholder="Paste a product description to try instead"
          value={pastedText}
          onChange={(e) => {
            const text = e.target.value;
            onSourceChange(text.trim() ? { type: 'text', text } : null);
          }}
        />
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Trying the rules...
        </div>
      )}

      {error && (
        <Alert variant="destructive" size="sm">
          <AlertIcon />
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}

      {!loading && !error && source && description && (
        <div className="rounded-md border bg-background p-2 text-xs">
          <span className="text-muted-foreground">Description: </span>
          <span className="font-mono">{description}</span>
        </div>
      )}

      {!source && (
        <p className="text-xs text-muted-foreground">
          Pick a product or paste text to see what each rule below reads from
          it.
        </p>
      )}
    </div>
  );
}
