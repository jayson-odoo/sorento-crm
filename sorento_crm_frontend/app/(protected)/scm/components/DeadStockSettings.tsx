'use client';

import { useEffect, useState } from 'react';
import { Loader2, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { useDeadStockDays, useSaveDeadStockDays } from '../hooks/useScmDashboard';

/**
 * Small, discoverable quick setting for the GLOBAL dead-stock threshold (days) -
 * the window that drives the dashboard's "Dead" status. Reads / writes
 * `/api/v1/scm/config/dead-stock-days`; saving invalidates the dashboard queries
 * so statuses and counts recompute. Writes require `scm.config.manage`.
 */
export function DeadStockSettings() {
  const { data, isLoading } = useDeadStockDays();
  const save = useSaveDeadStockDays();

  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');

  // Sync the input to the loaded value whenever the popover (re)opens.
  useEffect(() => {
    if (open && data != null) setValue(String(data));
  }, [open, data]);

  const parsed = Number(value);
  const valid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 3650;
  const dirty = data != null && parsed !== data;

  const onSave = async () => {
    if (!valid || !dirty) return;
    await save.mutateAsync(parsed);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <Settings2 className="size-4" />
          Settings
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <div className="space-y-3">
          <div>
            <Label htmlFor="dead-stock-days" className="text-sm font-medium">
              Dead-stock threshold (days)
            </Label>
            <p className="mt-1 text-xs text-muted-foreground">
              SKUs with no movement beyond this are flagged Dead.
            </p>
          </div>

          {isLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : (
            <Input
              id="dead-stock-days"
              type="number"
              min={1}
              max={3650}
              inputMode="numeric"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void onSave();
              }}
              aria-label="Dead-stock threshold in days"
            />
          )}

          {!valid && value !== '' ? (
            <p className="text-xs text-scm-stockout">Enter a whole number between 1 and 3650.</p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => void onSave()}
              disabled={!valid || !dirty || save.isPending}
            >
              {save.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
              Save
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
