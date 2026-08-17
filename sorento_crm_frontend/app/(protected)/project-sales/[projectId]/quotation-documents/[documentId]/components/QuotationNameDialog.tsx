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

/**
 * One text field, used to NAME something on a quotation: a scope today, a section heading when
 * S4 brings them back.
 *
 * The client asked whether they own these names: "for the Bill No 3 page 15/5, I can add section
 * myself one isit? if yes then very good, remember we need an edit view". They do. A scope or a
 * section label is free text copied off the customer's own bill of quantities, so one field is
 * the whole form, and the same dialog serves add and rename so the two cannot drift into two
 * different sets of rules.
 *
 * `window.prompt` would be the same field in a box the app cannot style, cannot validate and
 * cannot keep open while the request is in flight.
 */
export function QuotationNameDialog({
  open,
  onOpenChange,
  initialLabel,
  onSave,
  addTitle,
  renameTitle,
  fieldLabel,
  placeholder,
  hint,
  isSaving = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null or blank means this is a new name rather than a rename. */
  initialLabel: string | null;
  onSave: (label: string) => void | Promise<void>;
  addTitle: string;
  renameTitle: string;
  fieldLabel: string;
  placeholder?: string;
  hint?: string;
  isSaving?: boolean;
}) {
  const isEditing = Boolean(initialLabel && initialLabel.trim());
  const [label, setLabel] = React.useState(initialLabel ?? '');

  // The dialog stays mounted between opens, so without this the previous name is still sitting
  // in the field when the user opens it against a different one.
  React.useEffect(() => {
    if (open) setLabel(initialLabel ?? '');
  }, [open, initialLabel]);

  const trimmed = label.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? renameTitle : addTitle}</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!trimmed || isSaving) return;
            await onSave(trimmed);
          }}
        >
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="quotation-name-field">{fieldLabel}</Label>
              <Input
                id="quotation-name-field"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder={placeholder}
                autoFocus
              />
              {hint && (
                <p className="min-w-0 break-words text-xs text-muted-foreground">{hint}</p>
              )}
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || isSaving}>
              {isEditing ? 'Save name' : 'Add'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
