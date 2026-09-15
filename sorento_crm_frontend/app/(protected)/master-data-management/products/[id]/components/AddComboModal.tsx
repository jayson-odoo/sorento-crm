'use client';

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCreateProductCombo } from '../../hooks/useProductCombos';

interface AddComboModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productId: string;
  /** The new combo, so the section can open its parts table straight away. */
  onCreated?: (comboId: string) => void;
}

/**
 * Add a combo (AC-S1-2): a name and nothing else. The combo is created empty and
 * its parts are added on the section, one product at a time - so the name is the
 * only thing that has to be decided before it exists, and it is the catalogue's
 * own wording ("3 in 1"), not a code.
 *
 * A duplicate name is answered INLINE rather than in a toast: the field that has
 * to change is right here, and a toast would send the reader looking for it.
 */
export function AddComboModal({ open, onOpenChange, productId, onCreated }: AddComboModalProps) {
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useCreateProductCombo(productId);

  useEffect(() => {
    if (!open) return;
    setName('');
    setError(null);
  }, [open]);

  const canSave = name.trim().length > 0 && !create.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setError(null);
    try {
      const combo = await create.mutateAsync({ name: name.trim() });
      onCreated?.(combo.id);
      onOpenChange(false);
    } catch (caught) {
      setError((caught as Error).message || 'Failed to add the combo');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Add combo</DialogTitle>
            {/* sr-only: Radix warns without one, and the visible form needs no
                explanation (AC-X-3). Same shape PromotionTypeFormModal uses. */}
            <DialogDescription className="sr-only">
              Name a catalogue package on this product.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="combo-name">Name</Label>
              <Input
                id="combo-name"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  if (error) setError(null);
                }}
                placeholder="3 in 1"
                autoFocus
                disabled={create.isPending}
                aria-invalid={error ? true : undefined}
              />
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {create.isPending ? 'Saving...' : 'Add combo'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default AddComboModal;
