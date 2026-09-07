'use client';

/**
 * Brand fonts: the list (rename, delete) and the upload form that adds one.
 *
 * The name typed on upload IS the CSS family: the inspector lists it, the
 * layer stores it, and `@font-face` declares it, so the three cannot
 * disagree about what "Sorento Display" means. Renaming keeps that promise -
 * the backend rewrites every layer that named the old family in the same
 * transaction (PLAN-brand-font-manage.md).
 *
 * Delete asks nothing (D7): the trash becomes a countdown with Cancel, and
 * the server applies it when the window lapses. A font still named by any
 * template, tag sheet or draft fails at that point instead - the countdown
 * disappears and the toast carries the reason (`useDeferredAction` toasts a
 * failed commit on its own), and the row simply stays, exactly as it was.
 *
 * Extension is validated by the backend, which refuses anything that is not
 * a real font file - a JPEG accepted as one prints in the fallback typeface
 * without a word of complaint.
 */

import { useEffect, useState } from 'react';
import { Check, Loader2, Pencil, Trash2, Upload, X } from 'lucide-react';
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
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { renameAsset, uploadAsset, type KitAsset } from '../../services/assetService';

interface FontUploadDialogProps {
  open: boolean;
  /** Every brand font (`kind='font'` asset). Static Google fallbacks never appear here. */
  fonts: KitAsset[];
  onCancel: () => void;
  onUploaded: (asset: KitAsset) => void;
  /** A rename landed; `oldName` is what an open document may still carry (AC-5). */
  onRenamed: (asset: KitAsset, oldName: string) => void;
  /** The deferred delete committed - the row is gone on the server. */
  onDeleted: (id: string) => void;
}

interface FontRowProps {
  font: KitAsset;
  editing: boolean;
  editValue: string;
  saving: boolean;
  onEditValueChange: (value: string) => void;
  onStartEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDeleted: (id: string) => void;
}

/**
 * One row, one deferred delete: `entityId` is the font's own id, so two rows
 * deleted in quick succession each count down their own window rather than
 * fighting over one hook's idea of "the" pending record.
 */
function FontRow({
  font,
  editing,
  editValue,
  saving,
  onEditValueChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onDeleted,
}: FontRowProps) {
  const deletion = useDeferredAction({
    actionKey: 'dealer_kit_asset.delete',
    entityType: 'dealer_kit_asset',
    entityId: font.id,
    verb: 'Deleting',
    subject: font.name,
    surface: 'inline',
    // A delete started from another tab (or before a remount) still shows its
    // countdown here rather than a plain trash button (S6-05).
    watchFromMount: true,
    successMessage: `${font.name} deleted`,
    onCommitted: () => onDeleted(font.id),
  });

  return (
    <li className="flex items-center gap-1 rounded-md border px-2 py-1.5">
      {deletion.countdown ? (
        deletion.countdown
      ) : editing ? (
        <>
          <Input
            autoFocus
            className="h-7 flex-1 text-xs"
            value={editValue}
            onChange={(e) => onEditValueChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSaveEdit();
              if (e.key === 'Escape') onCancelEdit();
            }}
          />
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label={`Save ${font.name}`}
            disabled={saving || !editValue.trim()}
            onClick={onSaveEdit}
          >
            {saving ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Check className="size-3.5" />
            )}
          </Button>
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Cancel rename"
            disabled={saving}
            onClick={onCancelEdit}
          >
            <X className="size-3.5" />
          </Button>
        </>
      ) : (
        <>
          <span
            className="flex-1 truncate text-xs"
            style={{ fontFamily: font.name }}
            title={font.name}
          >
            {font.name}
          </span>
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label={`Rename ${font.name}`}
            onClick={onStartEdit}
          >
            <Pencil className="size-3.5" />
          </Button>
          <Button
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label={`Delete ${font.name}`}
            disabled={deletion.isBlocked}
            onClick={() => deletion.start()}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </>
      )}
    </li>
  );
}

export function FontUploadDialog({
  open,
  fonts,
  onCancel,
  onUploaded,
  onRenamed,
  onDeleted,
}: FontUploadDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setFiles([]);
      setName('');
      setEditingId(null);
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

  const cancelEdit = () => {
    setEditingId(null);
    setEditValue('');
  };

  const saveEdit = async (font: KitAsset) => {
    const next = editValue.trim();
    if (!next || next === font.name) {
      cancelEdit();
      return;
    }
    setSavingId(font.id);
    try {
      const updated = await renameAsset(font.id, next);
      onRenamed(updated, font.name);
      cancelEdit();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Rename failed');
    } finally {
      setSavingId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Brand fonts</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-4">
          {fonts.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">
              No brand fonts yet
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {fonts.map((font) => (
                <FontRow
                  key={font.id}
                  font={font}
                  editing={editingId === font.id}
                  editValue={editValue}
                  saving={savingId === font.id}
                  onEditValueChange={setEditValue}
                  onStartEdit={() => {
                    setEditingId(font.id);
                    setEditValue(font.name);
                  }}
                  onSaveEdit={() => void saveEdit(font)}
                  onCancelEdit={cancelEdit}
                  onDeleted={onDeleted}
                />
              ))}
            </ul>
          )}

          <div className="flex flex-col gap-3 border-t pt-3">
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
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Close
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
