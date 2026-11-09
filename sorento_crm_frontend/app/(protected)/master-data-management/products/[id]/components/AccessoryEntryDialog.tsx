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
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { AttachmentImage } from '@/components/common/AttachmentImage';
import { richPlainText } from '@/lib/dealer-kit/rich-text';
import type { AccessoryEntry, AccessoryEntryOverrides } from '../../../accessories/types/accessory.types';

const orNull = (html: string): string | null => (richPlainText(html).trim() === '' ? null : html);

/**
 * The pencil on a list row: which picture, name, spec lines and remark THIS list uses instead of
 * the accessory's own (blank = its own). Picture choice only for an accessory with several.
 */
export function AccessoryEntryDialog({
  entry,
  onOpenChange,
  onSave,
}: {
  entry: AccessoryEntry | null;
  onOpenChange: (open: boolean) => void;
  onSave: (overrides: AccessoryEntryOverrides) => void;
}) {
  const [imageId, setImageId] = useState('');
  const [name, setName] = useState('');
  const [spec, setSpec] = useState('');
  const [remark, setRemark] = useState('');

  useEffect(() => {
    if (!entry) return;
    setImageId(entry.entry?.image_id ?? '');
    setName(entry.entry?.name ?? '');
    setSpec(entry.entry?.spec ?? '');
    setRemark(entry.entry?.remark ?? '');
  }, [entry]);

  const pictures = entry?.kind === 'accessory' ? (entry.images ?? []) : [];
  // Each choice shows its picture beside its label, in the list and once picked.
  const withThumb = (option: SearchableSelectOption, size: string) => {
    const picture = pictures.find((p) => p.id === option.value);
    return (
      <span className="flex min-w-0 items-center gap-2">
        <AttachmentImage
          thumbUrl={picture?.thumb_url}
          url={picture?.url}
          className={`${size} shrink-0 rounded border object-cover`}
        />
        <span className="truncate">{option.label}</span>
      </span>
    );
  };

  return (
    <Dialog open={entry !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{entry?.name ?? ''}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {pictures.length > 1 ? (
            <div className="space-y-1.5">
              <Label>Picture choice</Label>
              <SearchableSelect
                aria-label="Picture choice"
                value={imageId}
                clearable
                placeholder="First picture"
                options={pictures.map((picture, index) => ({
                  value: picture.id,
                  label: picture.colour_name ?? `Picture ${index + 1}`,
                }))}
                onChange={(value: string) => setImageId(value)}
                renderOption={(option) => withThumb(option, 'size-10')}
                renderTriggerLabel={(option) => withThumb(option, 'size-6')}
              />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="entry-name">Name</Label>
            <Input id="entry-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label id="entry-spec-label">Spec lines</Label>
            <RichTextEditor
              value={spec}
              onChange={setSpec}
              toolbar="inline"
              minHeight={80}
              aria-labelledby="entry-spec-label"
            />
          </div>
          <div className="space-y-1.5">
            <Label id="entry-remark-label">Remark</Label>
            <RichTextEditor
              value={remark}
              onChange={setRemark}
              toolbar="inline"
              minHeight={60}
              aria-labelledby="entry-remark-label"
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setImageId('');
              setName('');
              setSpec('');
              setRemark('');
            }}
          >
            Use the accessory&apos;s own
          </Button>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() =>
              onSave({
                image_id: imageId || null,
                name: name.trim() === '' ? null : name.trim(),
                spec: orNull(spec),
                remark: orNull(remark),
              })
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
