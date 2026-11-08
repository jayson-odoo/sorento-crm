'use client';

import type { ReactNode } from 'react';
import { Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

/**
 * The ONE "Edit purchasing response" dialog, shared by the stock inquiry page and the new product
 * application detail so the two cannot drift: the response text, the host's own fields (`children`),
 * then Cancel, Save only and, when the host can send one, Update & Reply. A blank response disables
 * both buttons up front instead of failing after the click.
 */
export function PurchasingResponseDialog({
  open,
  onOpenChange,
  response,
  onResponseChange,
  onSave,
  onReply,
  canReply = false,
  saving = false,
  replying = false,
  saveDisabled = false,
  replyDisabled = false,
  replyTitle,
  saveGuideTarget,
  replyGuideTarget,
  description = 'Save updates the record only. Update & Reply saves your text and sends it to the contact.',
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  response: string;
  onResponseChange: (text: string) => void;
  onSave: () => void;
  onReply: () => void;
  /** Update & Reply is drawn only when true. */
  canReply?: boolean;
  saving?: boolean;
  replying?: boolean;
  /** Host rules on top of blank / saving / replying. */
  saveDisabled?: boolean;
  replyDisabled?: boolean;
  /** Why Update & Reply is off, when the text is not the reason. */
  replyTitle?: string;
  saveGuideTarget?: string;
  replyGuideTarget?: string;
  description?: ReactNode;
  children?: ReactNode;
}) {
  const blank = !response.trim();
  const blankTitle = 'Enter a purchasing response first.';
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        data-testid="purchasing-response-dialog"
      >
        <DialogHeader>
          <DialogTitle>Edit purchasing response</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="edit-purchasing-response">Purchasing response</Label>
          <Textarea
            id="edit-purchasing-response"
            value={response}
            onChange={(e) => onResponseChange(e.target.value)}
            placeholder="Response text..."
            rows={5}
            className="resize-none"
          />
        </div>
        {children}
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="outline"
            data-guide-target={saveGuideTarget}
            disabled={blank || saving || saveDisabled}
            title={blank ? blankTitle : undefined}
            onClick={onSave}
          >
            {saving ? 'Saving…' : 'Save only'}
          </Button>
          {canReply && (
            <Button
              variant="primary"
              data-guide-target={replyGuideTarget}
              disabled={blank || replying || replyDisabled}
              title={blank ? blankTitle : replyTitle}
              onClick={onReply}
            >
              <Send className="size-4 mr-1" />
              {replying ? 'Sending…' : 'Update & Reply'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PurchasingResponseDialog;
