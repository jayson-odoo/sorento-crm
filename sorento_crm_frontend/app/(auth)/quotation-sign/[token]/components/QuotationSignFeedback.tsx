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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import { formatMyrExact, formatQty } from '@/app/(protected)/project-sales/_shared/lib/money';
import {
  EMPTY_FEEDBACK,
  HINT_LABELS,
  MAX_MODEL,
  MAX_NOTE,
  feedbackError,
  hintsFor,
  type FeedbackDraft,
  type FeedbackHint,
  type FeedbackTarget,
} from './quotationSuggest';

/** Where the note points, and today's value there, in one line (mock v3 frame 4). */
export function targetWhere(target: FeedbackTarget): string {
  if (target.cell) {
    return `${target.itemLabel} · ${target.cell.label} (now ${target.cell.value})`;
  }
  return `${target.itemLabel} · ${target.scopeLabel}`;
}

/**
 * The feedback form for one item or one cell (PS-QUOTE-MATRIX R19): a note, and one optional
 * hint. A cell offers a quantity; an item a quantity, a price, removal, or another model at an
 * optional price. Sent as is: nothing is accepted or applied.
 */
export function FeedbackDialog({
  target,
  sending,
  onSend,
  onClose,
}: {
  /** Null closes the dialog. */
  target: FeedbackTarget | null;
  sending: boolean;
  onSend: (draft: FeedbackDraft) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = React.useState<FeedbackDraft>(EMPTY_FEEDBACK);
  const [tried, setTried] = React.useState(false);
  // A fresh form for every item or cell.
  React.useEffect(() => {
    setDraft(EMPTY_FEEDBACK);
    setTried(false);
  }, [target]);

  if (!target) return null;
  const error = feedbackError(target, draft);
  const hints = hintsFor(target);
  const set = (patch: Partial<FeedbackDraft>) => setDraft((previous) => ({ ...previous, ...patch }));
  const now = target.cell
    ? null
    : {
        quantity: formatQty(target.line.quantity),
        unit_price: formatMyrExact(target.line.unit_price),
      };

  return (
    <Dialog open onOpenChange={(next) => !next && !sending && onClose()}>
      <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-md overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Feedback</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <p className="break-words text-sm text-muted-foreground" data-testid="feedback-where">
            {targetWhere(target)}
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="quotation-feedback-note">Your note</Label>
            <Textarea
              id="quotation-feedback-note"
              rows={3}
              value={draft.note}
              maxLength={MAX_NOTE}
              disabled={sending}
              onChange={(event) => set({ note: event.target.value })}
            />
          </div>

          {target.cell ? (
            <div className="space-y-1.5">
              <Label htmlFor="quotation-feedback-value">Suggested quantity (optional)</Label>
              <Input
                id="quotation-feedback-value"
                inputMode="decimal"
                value={draft.value}
                disabled={sending}
                onChange={(event) =>
                  set({ value: event.target.value, hint: event.target.value.trim() ? 'quantity' : 'none' })
                }
              />
            </div>
          ) : (
            <fieldset className="space-y-2">
              <legend className="mb-1.5 text-sm font-medium">Suggestion (optional)</legend>
              <RadioGroup
                value={draft.hint}
                disabled={sending}
                onValueChange={(next) => set({ hint: next as FeedbackHint, value: '', model: '' })}
              >
                {hints.map((hint) => (
                  <div key={hint} className="flex items-center gap-2">
                    <RadioGroupItem value={hint} id={`quotation-feedback-hint-${hint}`} />
                    <Label htmlFor={`quotation-feedback-hint-${hint}`} className="font-normal">
                      {HINT_LABELS[hint]}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
              {(draft.hint === 'quantity' || draft.hint === 'unit_price') && (
                <div className="space-y-1.5">
                  <Label htmlFor="quotation-feedback-value">
                    {draft.hint === 'quantity'
                      ? `Suggested quantity (now ${now?.quantity})`
                      : `Suggested price (now ${now?.unit_price})`}
                  </Label>
                  <Input
                    id="quotation-feedback-value"
                    inputMode="decimal"
                    value={draft.value}
                    disabled={sending}
                    onChange={(event) => set({ value: event.target.value })}
                  />
                </div>
              )}
              {draft.hint === 'model_swap' && (
                <div className="space-y-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="quotation-feedback-model">Model name or code</Label>
                    <Input
                      id="quotation-feedback-model"
                      value={draft.model}
                      maxLength={MAX_MODEL}
                      disabled={sending}
                      onChange={(event) => set({ model: event.target.value })}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="quotation-feedback-value">Price (optional)</Label>
                    <Input
                      id="quotation-feedback-value"
                      inputMode="decimal"
                      value={draft.value}
                      disabled={sending}
                      onChange={(event) => set({ value: event.target.value })}
                    />
                  </div>
                </div>
              )}
            </fieldset>
          )}

          {tried && error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter className="flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" disabled={sending} onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={sending}
            onClick={() => {
              setTried(true);
              if (!error) onSend(draft);
            }}
          >
            Send feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The free note on the whole quotation: one box, sent with no items. */
export function NoteDialog({
  open,
  sending,
  onSend,
  onClose,
}: {
  open: boolean;
  sending: boolean;
  onSend: (note: string) => void;
  onClose: () => void;
}) {
  const [note, setNote] = React.useState('');
  React.useEffect(() => {
    if (open) setNote('');
  }, [open]);
  const tooLong = note.trim().length > 4000;
  return (
    <Dialog open={open} onOpenChange={(next) => !next && !sending && onClose()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-md">
        <DialogHeader>
          <DialogTitle>Leave a note</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-1.5">
          <Label htmlFor="quotation-feedback-free-note">Your note</Label>
          <Textarea
            id="quotation-feedback-free-note"
            rows={4}
            value={note}
            maxLength={4000}
            disabled={sending}
            onChange={(event) => setNote(event.target.value)}
          />
        </DialogBody>
        <DialogFooter className="flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" disabled={sending} onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={sending || !note.trim() || tooLong}
            onClick={() => onSend(note)}
          >
            Send feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
