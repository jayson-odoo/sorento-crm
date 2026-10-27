'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FileUp } from 'lucide-react';
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
import { FileDropzone } from '@/components/common/FileDropzone';
import { useImportJobDrawer } from '@/components/upload-activity';
import { toast } from '@/lib/toast';
import { useUploadCatalogPhotoReading } from '../hooks/useCatalogPhotoReadings';

const MAX_SIZE_MB = 50;

/**
 * Products > Actions > Extract photos from catalogue. One PDF, up to 50 MB; the read is a queued
 * job, so a success shows it in the upload drawer and lands on the review page.
 */
export function CatalogueUploadDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();
  const upload = useUploadCatalogPhotoReading();
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => {
    if (!open) setFiles([]);
  }, [open]);

  const submit = () => {
    const [file] = files;
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (reading) => {
        onOpenChange(false);
        notifyImportQueued();
        router.push(`/master-data-management/products/catalogue-photos/${reading.id}`);
      },
      onError: (error) => toast.error(error.message),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Extract photos from catalogue</DialogTitle>
          <DialogDescription className="sr-only">Choose the catalogue PDF to read.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <FileDropzone
            accept=".pdf"
            maxSizeMb={MAX_SIZE_MB}
            files={files}
            onFilesChange={setFiles}
            disabled={upload.isPending}
            hint="PDF only"
            aria-label="Catalogue PDF"
            onReject={(file, reason) =>
              toast.error(
                reason === 'size'
                  ? `${file.name} is over ${MAX_SIZE_MB} MB`
                  : reason === 'type'
                    ? `${file.name} is not a PDF`
                    : 'Choose one file',
              )
            }
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={upload.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={files.length === 0 || upload.isPending}>
            <FileUp className="size-4" />
            {upload.isPending ? 'Uploading' : 'Read catalogue'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
