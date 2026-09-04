'use client';

/**
 * "Save as size" - name the tag's current custom width/height so it comes
 * back as a preset in every future request's Tag Size dropdown, under
 * "Saved sizes" (S4, AC-S4-3, D2).
 *
 * Just a name: the width/height are what the tag is showing right now, not
 * re-entered here - editing them is what `/dealer-kit/tag-sizes` is for.
 */

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCreateTagSize } from '../../../../tag-sizes/hooks/useTagSizes';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  width_mm: number;
  height_mm: number;
}

export function SaveAsSizeDialog({ open, onOpenChange, width_mm, height_mm }: Props) {
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createMutation = useCreateTagSize();

  useEffect(() => {
    if (!open) return;
    setName('');
    setError(null);
  }, [open]);

  const submit = async () => {
    setError(null);
    try {
      await createMutation.mutateAsync({ name: name.trim(), width_mm, height_mm });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this size');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Save tag size</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-1">
          <div className="flex flex-col gap-2">
            <Label htmlFor="sas-name">Name</Label>
            <Input
              id="sas-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Shelf rail"
              autoFocus
            />
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Size</span>
            <span>
              {width_mm} x {height_mm} mm
            </span>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={createMutation.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name.trim() || createMutation.isPending}>
            {createMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
