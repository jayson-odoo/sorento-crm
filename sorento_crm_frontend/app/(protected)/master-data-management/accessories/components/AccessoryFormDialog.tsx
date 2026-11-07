'use client';

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
import { useCreateAccessory, useUpdateAccessory } from '../hooks/useAccessories';
import { AccessoryPictureControl } from './AccessoryPictureControl';
import type { Accessory } from '../types/accessory.types';

/** Create (no `accessory`) or edit (row click). A picture needs the record, so it shows on edit. */
export default function AccessoryFormDialog({
  open,
  onOpenChange,
  accessory,
  canEdit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessory: Accessory | null;
  canEdit: boolean;
}) {
  const [name, setName] = useState('');
  const [spec, setSpec] = useState('');
  const [image, setImage] = useState<Accessory['image']>(null);
  const create = useCreateAccessory();
  const update = useUpdateAccessory();

  useEffect(() => {
    if (!open) return;
    setName(accessory?.name ?? '');
    setSpec(accessory?.spec ?? '');
    setImage(accessory?.image ?? null);
  }, [open, accessory]);

  const trimmed = name.trim();
  const pending = create.isPending || update.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!trimmed) return;
    const write = { name: trimmed, spec: spec.trim() === '' ? null : spec.trim() };
    try {
      if (accessory) await update.mutateAsync({ id: accessory.id, write });
      else await create.mutateAsync(write);
      onOpenChange(false);
    } catch {
      // Toasted by the hook (a duplicate name says so); the modal stays open.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{accessory ? 'Edit accessory' : 'Add accessory'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={(e) => void submit(e)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="accessory-name">Name</Label>
            <Input
              id="accessory-name"
              value={name}
              maxLength={500}
              disabled={!canEdit}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="accessory-spec">Spec</Label>
            <Input
              id="accessory-spec"
              value={spec}
              maxLength={1000}
              disabled={!canEdit}
              onChange={(e) => setSpec(e.target.value)}
            />
          </div>
          {accessory ? (
            <AccessoryPictureControl
              accessory={{ ...accessory, image }}
              canEdit={canEdit}
              onChanged={setImage}
            />
          ) : null}
          {canEdit ? (
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!trimmed || pending}>
                {accessory ? 'Save' : 'Add accessory'}
              </Button>
            </DialogFooter>
          ) : null}
        </form>
      </DialogContent>
    </Dialog>
  );
}
