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
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { richPlainText } from '@/lib/dealer-kit/rich-text';
import { Label } from '@/components/ui/label';
import {
  useCreateAccessory,
  useReplaceAccessoryColours,
  useUpdateAccessory,
} from '../hooks/useAccessories';
import { AccessoryColoursField } from './AccessoryColoursField';
import { AccessoryPicturesField } from './AccessoryPicturesField';
import type { Accessory, AccessoryColour, AccessoryPicture } from '../types/accessory.types';

/** A rich value with no visible text is no value. */
const orNull = (html: string): string | null => (richPlainText(html).trim() === '' ? null : html);

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
  const [remark, setRemark] = useState('');
  const [pictures, setPictures] = useState<AccessoryPicture[]>([]);
  const [colours, setColours] = useState<AccessoryColour[]>([]);
  const replaceColours = useReplaceAccessoryColours();
  const create = useCreateAccessory();
  const update = useUpdateAccessory();

  useEffect(() => {
    if (!open) return;
    setName(accessory?.name ?? '');
    setSpec(accessory?.spec ?? '');
    setRemark(accessory?.remark ?? '');
    setPictures(accessory?.images ?? []);
    setColours((accessory?.colours ?? []).map(({ name, hex }) => ({ name: name ?? null, hex })));
  }, [open, accessory]);

  const trimmed = name.trim();
  const pending = create.isPending || update.isPending || replaceColours.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!trimmed) return;
    const write = { name: trimmed, spec: orNull(spec), remark: orNull(remark) };
    try {
      // The colours are their own list: saved right after the record they belong to.
      let id = accessory?.id;
      if (accessory) await update.mutateAsync({ id: accessory.id, write });
      else id = (await create.mutateAsync(write))?.id;
      if (id && (accessory || colours.length > 0)) await replaceColours.mutateAsync({ id, colours });
      onOpenChange(false);
    } catch {
      // Toasted by the hook (a duplicate name says so); the modal stays open.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
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
            <Label id="accessory-spec-label">Spec lines</Label>
            <RichTextEditor
              value={spec}
              onChange={setSpec}
              editable={canEdit}
              toolbar="inline"
              minHeight={80}
              aria-labelledby="accessory-spec-label"
            />
          </div>
          <div className="space-y-1.5">
            <Label id="accessory-remark-label">Remark</Label>
            <RichTextEditor
              value={remark}
              onChange={setRemark}
              editable={canEdit}
              toolbar="inline"
              minHeight={60}
              aria-labelledby="accessory-remark-label"
            />
          </div>
          {accessory ? (
            <AccessoryPicturesField
              accessoryId={accessory.id}
              pictures={pictures}
              canEdit={canEdit}
              onChanged={setPictures}
            />
          ) : null}
          <AccessoryColoursField colours={colours} canEdit={canEdit} onChange={setColours} />
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
