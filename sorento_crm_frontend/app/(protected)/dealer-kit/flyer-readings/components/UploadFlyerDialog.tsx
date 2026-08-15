'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FileUp } from 'lucide-react';

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

import { useUploadFlyerReading } from '../hooks/useFlyerReadings';

/**
 * Step one: hand over the PDF.
 *
 * No progress bar and no job to watch. Extraction runs inside the request - the
 * real 36 page flyer takes about a second - so this is a button that goes quiet
 * for a moment and then lands on the review screen. A queue here would buy a
 * pending state, a polling screen and a failure path, and nothing else.
 *
 * The backend refuses a non-PDF with a 400 and anything over 50 MB with a 413,
 * both in words, so those messages are shown as they arrive rather than
 * replaced with a generic one.
 */
export function UploadFlyerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { mutate, isPending } = useUploadFlyerReading();

  useEffect(() => {
    if (!open) {
      setFile(null);
      setError(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [open]);

  const submit = () => {
    if (!file) return;
    setError(null);
    mutate(
      { file },
      {
        onSuccess: (reading) => {
          onOpenChange(false);
          // Straight to the review screen. Reading a flyer and never looking at
          // what came back is the one path this feature must not have.
          router.push(`/dealer-kit/flyer-readings/${reading.id}`);
        },
        onError: (uploadError) => setError(uploadError.message),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Height-capped and scrollable so the submit button stays reachable on a phone. */}
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Read a flyer</DialogTitle>
          <DialogDescription>
            Upload the printed flyer as a PDF. It is read straight away, and you get a report of
            what was found before anything is created.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="dk-fr-file">Flyer PDF</Label>
            <Input
              id="dk-fr-file"
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => {
                setError(null);
                setFile(event.target.files?.[0] ?? null);
              }}
            />
            <p className="text-xs text-muted-foreground">
              Vector PDFs only, up to 50 MB. A scan has no text to read.
            </p>
          </div>

          {error && (
            <p className="text-sm text-destructive" data-testid="dk-fr-upload-error">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!file || isPending} data-testid="dk-fr-upload-submit">
            <FileUp className="size-4" />
            {isPending ? 'Reading the flyer' : 'Read the flyer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
