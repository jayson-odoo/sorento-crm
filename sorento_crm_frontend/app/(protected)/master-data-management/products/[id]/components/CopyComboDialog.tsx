'use client';

/**
 * COMBO-COPY-TO-PRODUCTS: copy one combo, as it is, to hand-picked products.
 * Plan: documentation/plans/products/PLAN-combo-copy-to-products-09nov.md (owner answers 9 Nov).
 *
 * Two steps in one modal, like CopyAccessoriesDialog: pick on the shared product grid, then a
 * confirm that reads the server's dry run. A picked product that already has a combo of this name
 * is listed with Skip / Overwrite (default Skip) and an "Overwrite all" switch; then one write.
 * The parent mounts it only while open, so every open starts from a clean slate.
 */

import { useMemo, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { distinctName } from '@/lib/product-display';
import { useCopyProductCombo } from '../../hooks/useProductCombos';
import type { ComboCopySummary } from '../../services/productComboService';
import {
  CopyCapNote,
  pickedLine,
  plural,
  useProductTargetPicker,
} from './ProductTargetPicker';

function codes(rows: { code: string }[]): string {
  return rows.map((row) => row.code).join(', ');
}

/** The confirm step's sentences above the conflict list, from the dry run. */
export function comboCopySummaryLines(
  name: string,
  summary: ComboCopySummary,
  cappedFrom: number | null = null,
): string[] {
  const lines = [
    cappedFrom !== null
      ? `Copy combo "${name}" to the first ${summary.targets.toLocaleString('en-US')} of ${cappedFrom.toLocaleString('en-US')} products.`
      : `Copy combo "${name}" to ${plural(summary.targets, 'product')}.`,
  ];
  if (summary.created > 0) {
    lines.push(
      `${plural(summary.created, 'product')} ${summary.created === 1 ? 'gets' : 'get'} it as a new combo.`,
    );
  }
  const parts = summary.skipped.filter((row) => row.reason === 'part');
  if (parts.length > 0) {
    lines.push(
      `${plural(parts.length, 'product')} ${parts.length === 1 ? 'is' : 'are'} skipped because ${parts.length === 1 ? 'it is' : 'they are'} a part of this combo: ${codes(parts)}.`,
    );
  }
  if (!summary.template_links_copied) {
    lines.push(
      'Price tag templates are not copied: that needs the permission to manage tag templates.',
    );
  }
  return lines;
}

export function CopyComboDialog({
  open,
  onOpenChange,
  sourceProductId,
  comboId,
  comboName,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  sourceProductId: string;
  comboId: string;
  comboName: string;
}) {
  const { preview, copy } = useCopyProductCombo(comboId);
  const { picked, overCap, cappedFrom, grid } = useProductTargetPicker(sourceProductId);
  const [summary, setSummary] = useState<ComboCopySummary | null>(null);
  // The conflicts picked to overwrite; every other conflict is skipped (owner default).
  const [overwrite, setOverwrite] = useState<Set<string>>(new Set());

  const conflicts = useMemo(() => summary?.conflicts ?? [], [summary]);
  const allOverwrite =
    conflicts.length > 0 &&
    conflicts.every((row) => overwrite.has(row.product_id));

  const goToConfirm = () => {
    preview.mutate(picked, {
      onSuccess: (result) => {
        setOverwrite(new Set());
        setSummary(result);
      },
    });
  };

  const choose = (productId: string, value: string) => {
    if (value !== 'skip' && value !== 'overwrite') return; // a second click on the chosen one
    setOverwrite((current) => {
      const next = new Set(current);
      if (value === 'overwrite') next.add(productId);
      else next.delete(productId);
      return next;
    });
  };

  const runCopy = () => {
    const overwriteIds = conflicts
      .map((row) => row.product_id)
      .filter((id) => overwrite.has(id));
    copy.mutate(
      { targetIds: picked, overwriteIds },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  const busy = preview.isPending || copy.isPending;
  const writes = summary ? summary.created + overwrite.size : 0;

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="flex max-h-[90dvh] w-[calc(100vw-2rem)] max-w-5xl flex-col"
        aria-describedby={undefined}
      >
        <DialogHeader>
          {/* pe-8: clear of the close X at 375px. */}
          <DialogTitle className="pe-8 break-words">
            Copy combo &quot;
            <span
              className="inline-block max-w-full truncate align-bottom"
              title={comboName}
            >
              {comboName}
            </span>
            &quot;{summary ? '' : ' to other products'}
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto">
          {summary ? (
            <div className="space-y-3 text-sm" data-testid="copy-combo-summary">
              {comboCopySummaryLines(comboName, summary, cappedFrom).map((line) => (
                <p key={line}>{line}</p>
              ))}
              {conflicts.length > 0 ? (
                <div className="space-y-2" data-testid="copy-combo-conflicts">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p>
                      {plural(conflicts.length, 'product')} already{' '}
                      {conflicts.length === 1 ? 'has' : 'have'} a combo called
                      &quot;{comboName}&quot;.
                    </p>
                    <label className="flex items-center gap-2">
                      <Switch
                        checked={allOverwrite}
                        onCheckedChange={(checked) =>
                          setOverwrite(
                            checked
                              ? new Set(conflicts.map((row) => row.product_id))
                              : new Set(),
                          )
                        }
                        aria-label="Overwrite all"
                      />
                      Overwrite all
                    </label>
                  </div>
                  <ul className="max-h-72 divide-y overflow-y-auto rounded-md border">
                    {conflicts.map((row) => {
                      const name = distinctName(row.code, row.name);
                      return (
                        <li
                          key={row.product_id}
                          className="flex flex-col gap-2 p-2 sm:flex-row sm:items-center sm:justify-between"
                        >
                          <div className="min-w-0">
                            <p
                              className="truncate font-medium"
                              title={row.code}
                            >
                              {row.code}
                            </p>
                            {name ? (
                              <p
                                className="truncate text-muted-foreground"
                                title={name}
                              >
                                {name}
                              </p>
                            ) : null}
                          </div>
                          <ToggleGroup
                            type="single"
                            variant="outline"
                            size="sm"
                            value={
                              overwrite.has(row.product_id)
                                ? 'overwrite'
                                : 'skip'
                            }
                            onValueChange={(value) =>
                              choose(row.product_id, value)
                            }
                            aria-label={`${row.code}: skip or overwrite`}
                          >
                            <ToggleGroupItem value="skip" className="px-3">
                              Skip
                            </ToggleGroupItem>
                            <ToggleGroupItem value="overwrite" className="px-3">
                              Overwrite
                            </ToggleGroupItem>
                          </ToggleGroup>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}
              <CopyCapNote />
            </div>
          ) : (
            grid
          )}
        </DialogBody>
        <DialogFooter className="flex-wrap items-center gap-2">
          {!summary ? (
            <span
              className="mr-auto text-sm text-muted-foreground"
              aria-live="polite"
            >
              {pickedLine(picked.length)}
            </span>
          ) : null}
          {summary ? (
            <Button
              variant="outline"
              onClick={() => setSummary(null)}
              disabled={busy}
            >
              Back
            </Button>
          ) : (
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={busy}
            >
              Cancel
            </Button>
          )}
          {summary ? (
            <Button onClick={runCopy} disabled={busy || writes === 0}>
              {copy.isPending ? (
                <LoaderCircle className="mr-1 size-4 animate-spin" />
              ) : null}
              Copy
            </Button>
          ) : (
            <Button
              onClick={goToConfirm}
              disabled={busy || picked.length === 0 || overCap}
            >
              {preview.isPending ? (
                <LoaderCircle className="mr-1 size-4 animate-spin" />
              ) : null}
              Next
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default CopyComboDialog;
