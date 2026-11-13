'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DatePicker } from '@/components/ui/date-picker';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatTimeAmPm, mytIso, parseTimeText, toMytParts } from '../lib/jobDates';
import type { ConfirmJobValues } from '../types/serviceJob.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialScheduledFrom?: string;
  onSubmit: (values: ConfirmJobValues) => void;
  isPending?: boolean;
}

export default function ConfirmDateDialog({
  open,
  onOpenChange,
  initialScheduledFrom,
  onSubmit,
  isPending,
}: Props) {
  const [date, setDate] = useState<Date | undefined>(undefined);
  const [time, setTime] = useState(formatTimeAmPm(10, 0));
  const [agreedBy, setAgreedBy] = useState('');
  const [error, setError] = useState<{ field: 'when' | 'agreed'; message: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    const parts = initialScheduledFrom ? toMytParts(initialScheduledFrom) : null;
    setDate(parts?.date);
    setTime(parts?.time ?? formatTimeAmPm(10, 0));
    setAgreedBy('');
    setError(null);
  }, [open, initialScheduledFrom]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = parseTimeText(time);
    if (!date) return setError({ field: 'when', message: 'Pick the date the customer agreed to.' });
    if (!parsed) return setError({ field: 'when', message: 'Enter the time, for example 10:00 am.' });
    if (!agreedBy.trim()) return setError({ field: 'agreed', message: 'Enter who agreed by name.' });
    setError(null);
    onSubmit({
      scheduled_from: mytIso(date, parsed.hour, parsed.minute),
      scheduled_to: null,
      customer_agreed_by: agreedBy.trim(),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Confirm date</DialogTitle>
          <DialogDescription className="sr-only">Date and time the customer agreed to.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Date</Label>
              <DatePicker value={date} onChange={setDate} ariaLabel="Date" portal required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="confirm-time">Time</Label>
              <Input
                id="confirm-time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                placeholder="10:00 am"
              />
            </div>
          </div>
          {error?.field === 'when' && (
            <p role="alert" className="text-sm text-destructive">
              {error.message}
            </p>
          )}
          {/* Always occupies its line: a preview that appears on blur would push the button down
              between mouse-down and mouse-up, and the first click on Confirm would be lost. */}
          <p data-testid="date-preview" className="min-h-5 text-sm text-muted-foreground">
            {date && parseTimeText(time)
              ? formatDateTimeInMalaysia(mytIso(date, parseTimeText(time)!.hour, parseTimeText(time)!.minute))
              : ''}
          </p>
          <div className="space-y-1">
            <Label htmlFor="confirm-agreed-by">Agreed by</Label>
            <Input
              id="confirm-agreed-by"
              value={agreedBy}
              onChange={(e) => setAgreedBy(e.target.value)}
            />
            {error?.field === 'agreed' && (
              <p role="alert" className="text-sm text-destructive">
                {error.message}
              </p>
            )}
          </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              Confirm date
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
