'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCreateProductSet, useUpdateProductSet } from '../hooks/useProductSets';
import type { ProductSet } from '../types/productSet.types';

interface ProductSetFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null creates. A set edits its code and name here; members are edited on the detail page. */
  productSet: ProductSet | null;
}

export function ProductSetFormModal({
  open,
  onOpenChange,
  productSet,
}: ProductSetFormModalProps) {
  const [setCode, setSetCode] = useState('');
  const [name, setName] = useState('');
  const create = useCreateProductSet();
  const update = useUpdateProductSet();
  const isSaving = create.isPending || update.isPending;

  useEffect(() => {
    if (!open) return;
    setSetCode(productSet?.set_code ?? '');
    setName(productSet?.name ?? '');
  }, [open, productSet]);

  const canSave = setCode.trim().length > 0 && name.trim().length > 0 && !isSaving;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    const payload = { set_code: setCode.trim(), name: name.trim() };
    if (productSet) {
      await update.mutateAsync({ id: productSet.id, data: payload });
    } else {
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{productSet ? 'Edit product set' : 'Add product set'}</DialogTitle>
            <DialogDescription>
              The code customers use for the whole assembly, such as SRTWC8608-RL. Members are
              added on the set&apos;s own page.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="product-set-code">Set code</Label>
              <Input
                id="product-set-code"
                value={setCode}
                onChange={(e) => setSetCode(e.target.value)}
                placeholder="SRTWC8608-RL"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="product-set-name">Name</Label>
              <Input
                id="product-set-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Washdown with rimless flushing, S-trap"
              />
            </div>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {isSaving ? 'Saving...' : productSet ? 'Save changes' : 'Create set'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
