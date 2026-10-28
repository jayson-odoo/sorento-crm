'use client';

import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useAddStop } from '../../hooks/useWalkthroughs';

/** Mirrors IMAGE_EXTENSIONS + VIDEO_EXTENSIONS in walkthrough_service.py / panorama.py. */
const ACCEPT = '.jpg,.jpeg,.png,.webp,.mp4,.mov,.m4v,.webm,.avi,.mkv,image/*,video/*';

/**
 * A stop is one spot in the showroom. The dialog closes as soon as the files are
 * handed over; the stitch runs on the worker and the stop shows Processing.
 */
export function AddStopDialog({
  walkthroughId,
  open,
  onOpenChange,
}: {
  walkthroughId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const addStop = useAddStop(walkthroughId);

  useEffect(() => {
    if (!open) {
      setTitle('');
      setFiles([]);
      setError(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [open]);

  const submit = () => {
    setError(null);
    addStop.mutate(
      { files, title: title.trim() },
      {
        onSuccess: () => onOpenChange(false),
        onError: (addError) => setError(addError.message),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a stop</DialogTitle>
          <DialogDescription>
            Stand in one spot. Upload a video of a slow turn, overlapping photos taken while
            turning, or one 360 photo.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="dk-wt-stop-title">Stop name</Label>
            <Input
              id="dk-wt-stop-title"
              value={title}
              maxLength={200}
              placeholder="e.g. Bathroom gallery"
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="dk-wt-stop-files">Video or photos</Label>
            <Input
              id="dk-wt-stop-files"
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            />
            {files.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {files.length === 1 ? files[0].name : `${files.length} files`}
              </p>
            )}
          </div>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={files.length === 0 || addStop.isPending}>
            {addStop.isPending ? 'Uploading...' : 'Add stop'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
