'use client';

/**
 * Add the brand's own typeface to the font list.
 *
 * The name typed here IS the CSS family: the inspector lists it, the layer
 * stores it, and `@font-face` declares it, so the three cannot disagree about
 * what "Sorento Display" means. Extension is validated by the backend, which
 * refuses anything that is not a real font file - a JPEG accepted as one prints
 * in the fallback typeface without a word of complaint.
 */

import { useEffect, useState } from 'react';
import { Loader2, Upload } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileDropzone } from '@/components/common/FileDropzone';
import { uploadAsset, type KitAsset } from '../../services/assetService';

interface FontUploadDialogProps {
  open: boolean;
  onCancel: () => void;
  onUploaded: (asset: KitAsset) => void;
}

export function FontUploadDialog({ open, onCancel, onUploaded }: FontUploadDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setFiles([]);
      setName('');
    }
  }, [open]);

  // The file's own name is the obvious default family, and re-typing it is a
  // step nobody needs.
  useEffect(() => {
    if (files[0] && !name) {
      setName(files[0].name.replace(/\.(woff2|ttf|otf)$/i, ''));
    }
  }, [files, name]);

  const handleUpload = async () => {
    const file = files[0];
    if (!file) return;
    setBusy(true);
    try {
      const asset = await uploadAsset({ file, kind: 'font', name: name.trim() });
      toast.success(`${asset.name} is available in the font list`);
      onUploaded(asset);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Upload a font</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-3">
          <FileDropzone
            accept=".woff2,.ttf,.otf"
            files={files}
            onFilesChange={setFiles}
            maxSizeMb={20}
            title="Font file"
          />
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">Font name</Label>
            <Input
              className="h-8 text-xs"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Sorento Display"
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={busy || files.length === 0 || !name.trim()}
          >
            {busy ? (
              <Loader2 className="mr-1 size-3.5 animate-spin" />
            ) : (
              <Upload className="mr-1 size-3.5" />
            )}
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
