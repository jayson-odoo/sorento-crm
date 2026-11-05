'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import type { AutocountWriteResult } from '../types/projectAutocountWrite.types';

const VERB_TEXT: Record<string, string> = {
  REMOVE_LINE: 'Remove line',
  CANCEL_BALANCE: 'Cancel balance',
  REPOINT_SO: 'Move to another order',
  MODEL_CHANGE: 'Change item',
  ADD_LINE: 'Add line',
  QTY_CHANGE: 'Change quantity',
  ADVANCE: 'Bring forward',
  DELAY: 'Delay',
};

function verbText(verb: string | null | undefined): string {
  if (!verb) return 'Change';
  return VERB_TEXT[verb] ?? verb.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

/**
 * AutoCount's own answer after a write (mock v2). Every write is followed by a read-back, so the
 * lines listed are the ones AutoCount holds, not the ones we sent. A skipped rate-only line and an
 * exploded product set are named (ruling R6), and what waits for AutoCount is listed with its
 * reason. A refusal is one sentence and no lines.
 */
export function AutocountWriteDialog({
  open,
  onOpenChange,
  title,
  result,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  result: AutocountWriteResult | null;
}) {
  const done = result?.outcome === 'done';
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {result ? (
            <>
              <p
                className={cn(
                  'text-sm font-medium break-words',
                  done ? 'text-success' : 'text-foreground',
                )}
                role="status"
              >
                {result.message}
              </p>

              {(result.warnings ?? []).map((warning, index) => {
                const text = typeof warning === 'string' ? warning : (warning.message ?? warning.code);
                return text ? (
                  <p
                    key={`${text}-${index}`}
                    className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm break-words"
                  >
                    {text}
                  </p>
                ) : null;
              })}

              {(result.lines ?? []).length > 0 && (
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2 font-medium">Line</th>
                        <th className="px-3 py-2 font-medium">Item</th>
                        <th className="px-3 py-2 font-medium">Description</th>
                        <th className="px-3 py-2 text-right font-medium">Qty</th>
                        <th className="px-3 py-2 text-right font-medium">Unit price</th>
                        <th className="px-3 py-2 font-medium">Location</th>
                        <th className="px-3 py-2 font-medium">Delivery</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.lines.map((line) => (
                        <tr key={`${line.line_no}-${line.item_code}`} className="border-t border-border">
                          <td className="px-3 py-2 tabular-nums">{line.line_no}</td>
                          <td className="max-w-[10rem] truncate px-3 py-2 font-medium" title={line.item_code ?? ''}>
                            {line.item_code}
                          </td>
                          <td className="max-w-[16rem] truncate px-3 py-2" title={line.description ?? ''}>
                            {line.description}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">{line.qty}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{line.unit_price}</td>
                          <td className="px-3 py-2">{line.location}</td>
                          <td className="px-3 py-2 tabular-nums">
                            {line.delivery_date ? formatDateInMalaysia(line.delivery_date) : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(result.skipped ?? []).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Not sent</p>
                  {result.skipped.map((line) => (
                    <p key={`${line.code}-${line.description}`} className="text-sm break-words">
                      {`${line.code ?? ''} ${line.description ?? ''}`.trim()}
                    </p>
                  ))}
                </div>
              )}

              {(result.exploded ?? []).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Sent as its parts</p>
                  {result.exploded.map((set) => (
                    <p key={set.code ?? 'set'} className="text-sm break-words">
                      {`${set.code ?? 'Set'}: ${set.components
                        .map((part) => `${part.code} x ${part.qty}`)
                        .join(', ')}`}
                    </p>
                  ))}
                </div>
              )}

              {(result.waiting ?? []).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Not changed yet</p>
                  {result.waiting.map((change, index) => (
                    <p key={`${change.verb}-${change.line_no}-${index}`} className="text-sm break-words">
                      {[
                        verbText(change.verb),
                        change.line_no != null ? `line ${change.line_no}` : null,
                        change.item_code,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      <span className="text-muted-foreground">{` - ${change.reason}`}</span>
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
