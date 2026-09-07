'use client';

/**
 * "Update <template>" (S6, D6) - confirms publishing the SELECTED line's
 * current design back to the template it was cloned from, as the next
 * version. The sibling checkbox (default on) additionally spreads the SAME
 * design and size onto every other line in this request already on that
 * template - the PUT/publish/sibling-apply sequence itself is the caller's
 * job (`onConfirm`); this is just the confirmation and the one decision
 * (the checkbox) the user makes here.
 */

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateName: string;
  /** The version this publish becomes, so the dialog can say which one. */
  nextVersionNo: number;
  /** How many OTHER lines in this request already use this template. 0 hides the checkbox. */
  siblingCount: number;
  saving: boolean;
  onConfirm: (applyToSiblings: boolean) => void;
}

export function UpdateTemplateDialog({
  open,
  onOpenChange,
  templateName,
  nextVersionNo,
  siblingCount,
  saving,
  onConfirm,
}: Props) {
  // Default ON (D6, AC-S6-2): republishing a template most often means every
  // line on it should catch up, not just the one being edited right now.
  const [applyToSiblings, setApplyToSiblings] = useState(true);

  useEffect(() => {
    if (!open) return;
    setApplyToSiblings(true);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Update &quot;{templateName}&quot;</DialogTitle>
          <DialogDescription>
            Publish this design as v{nextVersionNo} of {templateName}? Every request
            that picks {templateName} from now on gets this design.
          </DialogDescription>
        </DialogHeader>

        {siblingCount > 0 && (
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={applyToSiblings}
              onCheckedChange={(v) => setApplyToSiblings(!!v)}
            />
            <span>
              Also apply to the {siblingCount} other line{siblingCount === 1 ? '' : 's'} in
              this request that use {templateName}
            </span>
          </label>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => onConfirm(applyToSiblings)} disabled={saving}>
            {saving ? 'Publishing...' : 'Publish'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
