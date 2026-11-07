'use client';

import { useRef } from 'react';
import { ImagePlus, LoaderCircleIcon, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useAccessoryImage } from '../hooks/useAccessories';
import type { Accessory } from '../types/accessory.types';

/**
 * The accessory's picture: Upload when there is none, else the thumbnail with Replace and
 * Remove. Same behaviour as the combo's cover picture control; both lists refetch on success.
 * `onChanged` hands the new image up so the open modal shows it without waiting for the list.
 */
export function AccessoryPictureControl({
  accessory,
  canEdit,
  onChanged,
}: {
  accessory: Accessory;
  canEdit: boolean;
  onChanged: (image: Accessory['image']) => void;
}) {
  const { uploadMutateAsync, deleteMutateAsync, busy } = useAccessoryImage();
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      onChanged(await uploadMutateAsync({ id: accessory.id, file }));
    } catch {
      // The hook has already toasted the reason.
    } finally {
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const handleRemove = async () => {
    try {
      await deleteMutateAsync(accessory.id);
      onChanged(null);
    } catch {
      // Toasted by the hook.
    }
  };

  return (
    <div className="space-y-1.5">
      <Label>Picture</Label>
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
          aria-label={`${accessory.name} picture`}
          className="hidden"
          onChange={(event) => void handleFile(event.target.files?.[0])}
        />
        {accessory.image ? (
          <img
            src={accessory.image.url}
            alt=""
            className="size-14 shrink-0 rounded-md border object-cover"
          />
        ) : (
          <span className="text-sm text-muted-foreground">No picture</span>
        )}
        {canEdit ? (
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              {busy ? (
                <LoaderCircleIcon className="size-4 animate-spin" />
              ) : accessory.image ? (
                <Upload className="size-4" />
              ) : (
                <ImagePlus className="size-4" />
              )}
              {accessory.image ? 'Replace' : 'Upload picture'}
            </Button>
            {accessory.image ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void handleRemove()}
                disabled={busy}
              >
                <X className="size-4" />
                Remove
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
