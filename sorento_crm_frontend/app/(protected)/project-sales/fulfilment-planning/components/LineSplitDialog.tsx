'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from '@/lib/toast';
import { LineSplitEditor, type LineSplitEditorHandle } from './LineSplitEditor';

/**
 * OI-LINE-SPLIT v4: the split sheet page (UAC A, B, F; mock v4
 * `documentation/mockups/OI-LINE-SPLIT/index.html`), the board's "Split delivery". The sheet
 * and everything it does is `LineSplitEditor`; this host is the full-screen dialog, its
 * header (search, "Split lines only", Close / Cancel, Save) and closing after a Save.
 */
export function LineSplitDialog({
  open,
  psoId,
  focusLineId,
  onOpenChange,
}: {
  open: boolean;
  psoId: string;
  focusLineId?: string;
  onOpenChange: (open: boolean) => void;
}) {
  const editor = React.useRef<LineSplitEditorHandle | null>(null);

  const requestClose = () => {
    // Escape and the scrim never throw edits away; the Cancel button does (UAC B5, A12).
    if (editor.current?.isDirty()) {
      toast('Unsaved changes: Save or Cancel');
      return;
    }
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) requestClose();
      }}
    >
      <DialogContent
        variant="fullscreen"
        showCloseButton={false}
        className="gap-0 overflow-hidden p-0 max-md:inset-0 max-md:rounded-none"
        // Escape during a drag puts the drag back; it never closes the page (UAC A10).
        onEscapeKeyDown={(event) => {
          if (editor.current?.isDragging()) event.preventDefault();
        }}
      >
        <LineSplitEditor
          psoId={psoId}
          active={open}
          focusLineId={focusLineId}
          onSaved={() => onOpenChange(false)}
          handleRef={editor}
          testId="line-split-dialog"
          renderHeader={({ subtitle, locations, searchControls, dirty, canSave, save }) => (
            <DialogHeader className="mb-0 flex flex-col gap-3 space-y-0 border-b border-border px-4 py-3 text-start sm:text-start lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <DialogTitle className="truncate">Split delivery</DialogTitle>
                <DialogDescription className="truncate text-xs">
                  {subtitle}
                </DialogDescription>
                {locations ? (
                  <p className="truncate text-xs text-muted-foreground md:hidden">
                    {locations}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {searchControls}
                <div className="ms-auto flex items-center gap-2">
                  {/* ONE secondary button (UAC A12): Close, or Cancel once there is
                      something to discard. Escape still refuses while dirty. */}
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => onOpenChange(false)}
                  >
                    {dirty ? 'Cancel' : 'Close'}
                  </Button>
                  <Button type="button" disabled={!canSave} onClick={save}>
                    Save
                  </Button>
                </div>
              </div>
            </DialogHeader>
          )}
        />
      </DialogContent>
    </Dialog>
  );
}

export default LineSplitDialog;
