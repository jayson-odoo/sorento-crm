'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  onSubmit: (reason: string) => void;
  isPending?: boolean;
}

export default function ReasonDialog({ open, onOpenChange, title, onSubmit, isPending }: Props) {
  const [reason, setReason] = useState('');
  useEffect(() => {
    if (open) setReason('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">Enter the reason.</DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
        <div className="space-y-1">
          <Label htmlFor="move-reason">Reason</Label>
          <Textarea id="move-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Back
          </Button>
          <Button disabled={!reason.trim() || isPending} onClick={() => onSubmit(reason.trim())}>
            {title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
