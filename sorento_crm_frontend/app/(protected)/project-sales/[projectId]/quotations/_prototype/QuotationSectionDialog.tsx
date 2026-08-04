'use client';

import * as React from 'react';
import { Trash2 } from 'lucide-react';
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
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';

/**
 * Adds or renames one section heading inside a scope.
 *
 * The client asked whether they own these: "for the Bill No 3 page 15/5, I can add section
 * myself one isit? if yes then very good, remember we need an edit view". They do. A section
 * label is free text copied off the customer's own bill of quantities (AC-C3) - the CRM models
 * no bill or page numbering of its own, because the next customer numbers theirs differently.
 * One field is therefore the whole form, and the same dialog serves add and rename so the two
 * can never drift into two different sets of rules.
 */
export function QuotationSectionDialog({
  open,
  onOpenChange,
  initialLabel,
  onSave,
  onDelete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null or blank means this is a new section rather than a rename. */
  initialLabel: string | null;
  onSave: (label: string) => void;
  onDelete?: () => void | Promise<void>;
}) {
  const isEditing = Boolean(initialLabel && initialLabel.trim());
  const [label, setLabel] = React.useState(initialLabel ?? '');
  const [confirmingDelete, setConfirmingDelete] = React.useState(false);

  // The dialog stays mounted between opens, so without this the previous section's name is
  // still sitting in the field when the user opens it against a different one.
  React.useEffect(() => {
    if (open) setLabel(initialLabel ?? '');
  }, [open, initialLabel]);

  const trimmed = label.trim();

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="w-full max-w-md">
          <DialogHeader>
            <DialogTitle>{isEditing ? 'Rename section' : 'Add a section'}</DialogTitle>
          </DialogHeader>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!trimmed) return;
              onSave(trimmed);
              onOpenChange(false);
            }}
          >
            <DialogBody className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="quotation-section-name">Section name</Label>
                <Input
                  id="quotation-section-name"
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  placeholder="e.g. BILL NO 3 PAGE 15/5"
                  autoFocus
                />
                <p className="min-w-0 break-words text-xs text-muted-foreground">
                  Copied from the customer&apos;s own bill of quantities, so it can read however
                  they write it.
                </p>
              </div>
            </DialogBody>

            {/* Delete sits away from Save on wide screens and above it on a phone, so the
                destructive action is never the button under a thumb reaching for Save. */}
            <DialogFooter className="flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              {isEditing && onDelete ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setConfirmingDelete(true)}
                  className="text-destructive"
                >
                  <Trash2 className="size-4" aria-hidden />
                  Delete section
                </Button>
              ) : (
                <span />
              )}
              <div className="flex flex-wrap gap-2 sm:justify-end">
                <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!trimmed}>
                  {isEditing ? 'Save name' : 'Add section'}
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Rendered as a sibling, not inside the dialog above: nesting two Radix dialogs fights
          over focus, and the confirmation has to survive its parent closing on success. */}
      {onDelete && (
        <ConfirmDeleteDialog
          open={confirmingDelete}
          onOpenChange={setConfirmingDelete}
          description={
            <>
              Remove the heading <span className="font-medium">{initialLabel}</span>? Every line
              under it stays on the scope, in the same order - only the heading goes. This action
              cannot be undone.
            </>
          }
          onDelete={async () => {
            await onDelete();
          }}
          successMessage="Section removed"
          onSuccess={() => onOpenChange(false)}
        />
      )}
    </>
  );
}
