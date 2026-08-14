'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FileText, FileUp } from 'lucide-react';

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import LinkAttachmentBrowserDialog, {
  type LinkAttachmentSelection,
} from '@/components/common/LinkAttachmentBrowserDialog';

import { useCreateFlyerReadingFromAttachment, useUploadFlyerReading } from '../hooks/useFlyerReadings';

/** The two places a flyer can come from. Upload stays the default. */
type FlyerSource = 'upload' | 'library';

/**
 * Every spelling of PDF the reader accepts, mirroring `PDF_MIME_TYPES` in
 * `app/services/dealer_kit/flyer_reading_service.py`. A flyer filed under one
 * of the rarer ones is still a flyer, and a picker that hid it would make it
 * unreachable through the UI while the API happily read it.
 *
 * The backend ALSO lets `application/octet-stream`, `binary/octet-stream` and a
 * missing mime through, because those say "we did not know" rather than "not a
 * PDF" - typically a row whose type was lost on import. That leniency is
 * deliberately NOT mirrored here: filtering the library on octet-stream would
 * list every binary blob in the system and the picker would stop being a
 * shortlist. The route stays lenient, the picker stays strict. Do not widen
 * this to close the gap.
 */
const PDF_MIME_TYPES = [
  'application/pdf',
  'application/x-pdf',
  'application/acrobat',
  'applications/vnd.pdf',
  'text/pdf',
  'text/x-pdf',
];

/**
 * Step one: point at the PDF.
 *
 * Two sources, because there are two real starting points: the file the agency
 * just sent, and the file marketing filed in Resource Management months ago.
 * The second one used to mean downloading it out of the CRM and uploading it
 * back in, which is a round trip the system can spare them.
 *
 * No progress bar and no job to watch. Extraction runs inside the request, and
 * it is not quick: measured at 17 to 18 s for the real 36 page flyer on a quiet
 * machine, 39 to 62 s on a loaded one. So this is a button that goes quiet for
 * a while and then lands on the review screen. A queue here would buy a pending
 * state, a polling screen and a failure path; it is on the backlog for when
 * artwork rasterisation makes the read longer still.
 *
 * The backend refuses a non-PDF with a 400 and anything over 50 MB with a 413,
 * both in words and identically for both sources, so those messages are shown
 * as they arrive rather than replaced with a generic one.
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
  const [source, setSource] = useState<FlyerSource>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [picked, setPicked] = useState<LinkAttachmentSelection | null>(null);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useUploadFlyerReading();
  const fromAttachment = useCreateFlyerReadingFromAttachment();
  const isPending = upload.isPending || fromAttachment.isPending;

  useEffect(() => {
    if (!open) {
      setSource('upload');
      setFile(null);
      setPicked(null);
      setBrowserOpen(false);
      setError(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [open]);

  // Straight to the review screen, from either source. Reading a flyer and
  // never looking at what came back is the one path this feature must not have.
  const onRead = (readingId: string) => {
    onOpenChange(false);
    router.push(`/dealer-kit/flyer-readings/${readingId}`);
  };

  const submit = () => {
    setError(null);
    if (source === 'upload') {
      if (!file) return;
      upload.mutate(
        { file },
        {
          onSuccess: (reading) => onRead(reading.id),
          onError: (readError) => setError(readError.message),
        },
      );
      return;
    }
    if (!picked) return;
    fromAttachment.mutate(
      { attachmentId: picked.id },
      {
        onSuccess: (reading) => onRead(reading.id),
        onError: (readError) => setError(readError.message),
      },
    );
  };

  const canSubmit = source === 'upload' ? Boolean(file) : Boolean(picked);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Height-capped and scrollable so the submit button stays reachable on a phone. */}
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Read a flyer</DialogTitle>
          <DialogDescription>
            The flyer is read straight away and can take up to a minute. You get a report of what
            was found before anything is created.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={source}
          onValueChange={(next) => {
            setSource(next as FlyerSource);
            setError(null);
          }}
          className="py-2"
        >
          <TabsList variant="line" className="w-full">
            <TabsTrigger value="upload" data-testid="dk-fr-source-upload">
              Upload a file
            </TabsTrigger>
            <TabsTrigger value="library" data-testid="dk-fr-source-library">
              Choose from Files
            </TabsTrigger>
          </TabsList>

          {/*
            Both panels stay mounted. The file input is a DOM control, so
            unmounting it on a tab switch would throw away a chosen file the
            moment the designer looked at the other source and came back.
          */}
          <TabsContent
            value="upload"
            forceMount
            className="data-[state=inactive]:hidden flex flex-col gap-2"
          >
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
          </TabsContent>

          <TabsContent
            value="library"
            forceMount
            className="data-[state=inactive]:hidden flex flex-col gap-2"
          >
            <Label>Flyer PDF</Label>
            <div className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-2">
                <FileText className="size-4 shrink-0 text-muted-foreground" />
                <span
                  className="truncate text-sm"
                  title={picked?.name ?? undefined}
                  data-testid="dk-fr-library-selection"
                >
                  {picked ? picked.name : 'No file chosen'}
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={() => {
                  setError(null);
                  setBrowserOpen(true);
                }}
                disabled={isPending}
                data-testid="dk-fr-library-browse"
              >
                {picked ? 'Change file' : 'Choose a file'}
              </Button>
            </div>
          </TabsContent>
        </Tabs>

        {/* One place for the failure, whichever source produced it. */}
        {error && (
          <p className="text-sm text-destructive" data-testid="dk-fr-upload-error">
            {error}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit || isPending} data-testid="dk-fr-upload-submit">
            <FileUp className="size-4" />
            {isPending ? 'Reading the flyer' : 'Read the flyer'}
          </Button>
        </DialogFooter>

        {browserOpen && (
          <LinkAttachmentBrowserDialog
            open={browserOpen}
            onOpenChange={setBrowserOpen}
            maxSelections={1}
            mimeTypes={PDF_MIME_TYPES}
            title="Choose a flyer"
            confirmLabel="Use this file"
            onConfirm={(selected) => {
              const [first] = selected;
              if (first) setPicked(first);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
