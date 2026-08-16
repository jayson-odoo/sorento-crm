'use client';

import { useEffect, useRef, useState } from 'react';
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
 * The dialog closes as soon as the flyer is handed over, and goes nowhere. The
 * read is a queued job now (measured at 18 s for the real 36 page flyer, which
 * is more than any gateway will hold a request for), so there is nothing to
 * navigate to yet: the row is already at the top of the Flyers list saying
 * Processing, and that is where the toast points.
 *
 * What the backend can still refuse while this dialog is open is what it can
 * decide without opening the file: anything over 50 MB is a 413 on both sources,
 * and a library file whose recorded mime is not a PDF is a 400. Those messages
 * are shown as they arrive rather than replaced with a generic one. Everything
 * only the bytes can reveal - an uploaded file that is not really a PDF, a
 * password protected one - happens after this dialog is gone and lands on the
 * row as Failed with the same words.
 */
export function UploadFlyerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
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

  // Handed over, from either source: the dialog gets out of the way and the
  // designer is back on the list with their flyer already on it. A refusal
  // keeps the dialog open, because the file they chose is the thing to change.
  const onHandedOver = () => onOpenChange(false);

  const submit = () => {
    setError(null);
    if (source === 'upload') {
      if (!file) return;
      upload.mutate(
        { file },
        {
          onSuccess: onHandedOver,
          onError: (readError) => setError(readError.message),
        },
      );
      return;
    }
    if (!picked) return;
    fromAttachment.mutate(
      { attachmentId: picked.id },
      {
        onSuccess: onHandedOver,
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
            You get a report of what was found before anything is created.
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
