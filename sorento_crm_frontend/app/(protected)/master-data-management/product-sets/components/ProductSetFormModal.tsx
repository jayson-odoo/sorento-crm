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
import { useCreateProductSet } from '../hooks/useProductSets';

interface ProductSetFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Create only. Editing an existing set - code, name, members, price override -
 * happens on the set's own detail page, in place, behind that page's own
 * Edit/Save/Cancel toggle, so a set never has two different ways to be edited.
 */
export function ProductSetFormModal({ open, onOpenChange }: ProductSetFormModalProps) {
  const [setCode, setSetCode] = useState('');
  const [name, setName] = useState('');
  const create = useCreateProductSet();
  const isSaving = create.isPending;

  useEffect(() => {
    if (!open) return;
    setSetCode('');
    setName('');
  }, [open]);

  const canSave = setCode.trim().length > 0 && name.trim().length > 0 && !isSaving;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    await create.mutateAsync({ set_code: setCode.trim(), name: name.trim() });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Add product set</DialogTitle>
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
              {isSaving ? 'Saving...' : 'Create set'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
