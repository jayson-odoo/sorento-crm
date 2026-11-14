'use client';

/**
 * Choose a picture for a layer: the bound product's own photos, or the library.
 *
 * Two tabs, in that order, because that is the order a designer wants them
 * (D30). The product's photos are what a tag is normally made of - the primary
 * shot, the accessory shot, the cutaway - and the library is where the badges,
 * icons and diagrams live. Uploading happens in place: leaving the editor to add
 * one badge and coming back to a canvas that has lost its selection is how a
 * layout gets rebuilt twice.
 */

import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, Search, Upload } from 'lucide-react';
import { cn } from '@/lib/utils';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FileDropzone } from '@/components/common/FileDropzone';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type {
  ImageSource,
  TagImage,
} from '@/lib/dealer-kit/tag-template-types';
import {
  listAssets,
  uploadAsset,
  type AssetKind,
  type KitAsset,
} from '../../services/assetService';

// Narrowed by KIND, the same field the spec icon picker reads (`libraryKind`), so "Icons" here
// and the icons a spec value can carry are one list (SPEC-ICON-PICKER-UX).
const LIBRARY_KINDS: { value: string; label: string }[] = [
  { value: '__all__', label: 'All artwork' },
  { value: 'badge', label: 'Badges' },
  { value: 'icon', label: 'Icons' },
  { value: 'diagram', label: 'Diagrams' },
  { value: 'logo', label: 'Logos' },
];

interface AssetPickerDialogProps {
  open: boolean;
  /** The bound product's photos. Empty = the tab shows its own empty state. */
  productImages: TagImage[];
  /** A badge layer only takes library artwork, so its product tab is hidden. */
  allowProductPhotos?: boolean;
  /** What an upload from this dialog is filed as. */
  uploadKind?: AssetKind;
  /**
   * Manage ONE kind (the icon library, from a Feature icons layer or a spec value): the library lists only that
   * kind, an upload is filed as it, and the new asset stays in the list instead of being picked,
   * so the next one can be added straight away.
   */
  libraryKind?: AssetKind;
  title?: string;
  /** The footer button's words: "Cancel" when picking one, "Done" when adding several. */
  closeLabel?: string;
  /**
   * Select mode (with `onDone`): a tile click toggles a selected state and applies nothing; Done
   * hands back the selection in the order it was made, starting from these ids. Cancel, the X and
   * a click away discard it. An upload joins the grid already selected. Library tiles only:
   * product photos still go through `onPick`, so pair this with `allowProductPhotos={false}`.
   */
  selectedIds?: string[];
  onDone?: (assetIds: string[]) => void;
  onCancel: () => void;
  onPick?: (source: ImageSource) => void;
  /**
   * Pick several (product photos and library artwork alike): a tile click toggles a tick, the
   * footer counts the picks, and Done hands them back in the order they were made. An upload
   * joins the selection. Cancel, the X and a click away discard it.
   */
  onPickMany?: (sources: ImageSource[]) => void;
}

const MAX_UPLOAD_MB = 20;

const sameSource = (a: ImageSource, b: ImageSource) =>
  a.type === 'asset'
    ? b.type === 'asset' && a.assetId === b.assetId
    : b.type === 'product_attachment' && a.attachmentId === b.attachmentId;

export function AssetPickerDialog({
  open,
  productImages,
  allowProductPhotos = true,
  uploadKind: uploadKindProp = 'decorative',
  libraryKind,
  title = 'Choose an image',
  closeLabel = 'Cancel',
  selectedIds,
  onDone,
  onCancel,
  onPick,
  onPickMany,
}: AssetPickerDialogProps) {
  const selecting = onDone !== undefined;
  const many = !selecting && onPickMany !== undefined;
  const uploadKind = libraryKind ?? uploadKindProp;
  const [tab, setTab] = useState(allowProductPhotos ? 'product' : 'library');
  const [assets, setAssets] = useState<KitAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [tagFilter, setTagFilter] = useState('__all__');
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const [picks, setPicks] = useState<ImageSource[]>([]);

  const toggle = (id: string) =>
    setSelection((ids) => (ids.includes(id) ? ids.filter((other) => other !== id) : [...ids, id]));
  const togglePick = (source: ImageSource) =>
    setPicks((current) =>
      current.some((pick) => sameSource(pick, source))
        ? current.filter((pick) => !sameSource(pick, source))
        : [...current, source],
    );
  const isPicked = (source: ImageSource) => picks.some((pick) => sameSource(pick, source));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listAssets({
        query,
        ...(libraryKind
          ? { kind: libraryKind }
          : { kind: tagFilter === '__all__' ? undefined : tagFilter }),
        limit: 100,
      });
      setAssets(rows);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to load artwork',
      );
    } finally {
      setLoading(false);
    }
  }, [query, tagFilter, libraryKind]);

  useEffect(() => {
    if (!open) return;
    setTab(allowProductPhotos ? 'product' : 'library');
    setFiles([]);
    setSelection(selectedIds ?? []);
    setPicks([]);
    // Seeded on open only: the host's list changes on Done, never while the dialog is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, allowProductPhotos]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  // One file in plain pick mode is uploaded and used at once; otherwise every file joins the
  // library (and the selection, when there is one) so the next can be added straight away.
  const uploadAndUse = !libraryKind && !selecting && !many && files.length <= 1;

  const handleUpload = useCallback(async () => {
    if (files.length === 0) return;
    setUploading(true);
    const failed: File[] = [];
    const added: KitAsset[] = [];
    // One request per file, in order: the endpoint takes a single file.
    for (const file of files) {
      try {
        const asset = await uploadAsset({
          file,
          kind: uploadKind,
          tags: uploadKind === 'decorative' ? undefined : [uploadKind],
        });
        added.push(asset);
        if (uploadAndUse) continue;
        setAssets((rows) => [
          ...rows.filter((row) => row.id !== asset.id),
          asset,
        ]);
        if (selecting) {
          setSelection((ids) => (ids.includes(asset.id) ? ids : [...ids, asset.id]));
        }
        if (many) {
          const source: ImageSource = { type: 'asset', assetId: asset.id };
          setPicks((current) =>
            current.some((pick) => sameSource(pick, source)) ? current : [...current, source],
          );
        }
      } catch (error) {
        failed.push(file);
        toast.error(`${file.name}: ${error instanceof Error ? error.message : 'Upload failed'}`);
      }
    }
    setFiles(failed);
    setUploading(false);
    if (added.length === 0) return;
    toast.success(
      added.length === 1
        ? `${added[0].name} added to the library`
        : `${added.length} images added to the library`,
    );
    if (uploadAndUse) onPick?.({ type: 'asset', assetId: added[0].id });
  }, [files, uploadKind, uploadAndUse, selecting, many, onPick]);

  const rejectFile = useCallback((file: File, reason: 'type' | 'size' | 'extra') => {
    toast.error(
      reason === 'size'
        ? `${file.name} is over ${MAX_UPLOAD_MB} MB`
        : `${file.name} is not a PNG, JPG, WebP or SVG`,
    );
  }, []);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              {allowProductPhotos && (
                <TabsTrigger value="product">Product photos</TabsTrigger>
              )}
              <TabsTrigger value="library">Asset library</TabsTrigger>
            </TabsList>

            {allowProductPhotos && (
              <TabsContent value="product" className="mt-3">
                {productImages.length === 0 ? (
                  <p className="py-8 text-center text-xs text-muted-foreground">
                    This block is not bound to a product, or the product has no
                    photos you can use. Bind the block to a product, or pick
                    from the asset library.
                  </p>
                ) : (
                  <div className="grid max-h-80 grid-cols-4 gap-2 overflow-auto">
                    {productImages.map((image) => {
                      const source: ImageSource = {
                        type: 'product_attachment',
                        attachmentId: image.attachment_id,
                      };
                      const picked = many && isPicked(source);
                      return (
                        <button
                          key={image.attachment_id}
                          type="button"
                          className={cn(
                            'group relative aspect-square overflow-hidden rounded border hover:ring-2 hover:ring-primary',
                            picked && 'border-primary ring-2 ring-primary',
                          )}
                          onClick={() => (many ? togglePick(source) : onPick?.(source))}
                          aria-pressed={many ? picked : undefined}
                        >
                          {many && <PickTick picked={picked} />}
                          <img
                            src={image.url}
                            alt=""
                            className="size-full object-contain"
                          />
                          {image.is_primary && (
                            <span className="absolute left-1 top-1 rounded bg-primary px-1 text-2xs text-primary-foreground">
                              Primary
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
            )}

            <TabsContent value="library" className="mt-3 flex flex-col gap-3">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="h-8 pl-7 text-xs"
                    placeholder="Search artwork"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                {!libraryKind && (
                  <div className="w-40">
                    <SearchableSelect
                      value={tagFilter}
                      onChange={setTagFilter}
                      options={LIBRARY_KINDS}
                      size="sm"
                    />
                  </div>
                )}
              </div>

              {loading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="size-4 animate-spin text-muted-foreground" />
                </div>
              ) : assets.length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  Nothing in the library yet. Upload artwork below.
                </p>
              ) : (
                <div className="grid max-h-64 grid-cols-5 gap-2 overflow-auto">
                  {assets.map((asset) => {
                    // A rendition for the grid, never 200 originals.
                    const preview = asset.thumb_url ?? asset.url;
                    const source: ImageSource = { type: 'asset', assetId: asset.id };
                    const ticked = selecting || many;
                    const picked = selecting
                      ? selection.includes(asset.id)
                      : many && isPicked(source);
                    return (
                      <div key={asset.id} className="relative">
                        <button
                          type="button"
                          // The selectable-tile pattern of the catalogue picker
                          // (`dealer-kit/components/TileGrid.tsx`): ring + check.
                          className={cn(
                            'relative flex w-full flex-col items-center gap-1 rounded border p-1 hover:ring-2 hover:ring-primary',
                            picked && 'border-primary ring-2 ring-primary',
                          )}
                          onClick={() =>
                            selecting
                              ? toggle(asset.id)
                              : many
                                ? togglePick(source)
                                : onPick?.(source)
                          }
                          aria-pressed={ticked ? picked : undefined}
                          title={asset.name}
                        >
                          {ticked && <PickTick picked={picked} />}
                          <span className="flex aspect-square w-full items-center justify-center overflow-hidden">
                            {preview ? (
                              <img
                                src={preview}
                                alt=""
                                className="size-full object-contain"
                              />
                            ) : (
                              <span className="text-2xs text-muted-foreground">
                                No preview
                              </span>
                            )}
                          </span>
                          <span className="w-full truncate text-2xs">
                            {asset.name}
                          </span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex flex-col gap-2 border-t pt-3">
                <FileDropzone
                  accept=".png,.jpg,.jpeg,.webp,.svg"
                  multiple
                  files={files}
                  onFilesChange={setFiles}
                  onReject={rejectFile}
                  maxSizeMb={MAX_UPLOAD_MB}
                  title="Upload artwork"
                />
                <div className="flex justify-end">
                  <Button
                    size="sm"
                    className="h-7 text-xs"
                    onClick={handleUpload}
                    disabled={files.length === 0 || uploading}
                  >
                    {uploading ? (
                      <Loader2 className="mr-1 size-3.5 animate-spin" />
                    ) : (
                      <Upload className="mr-1 size-3.5" />
                    )}
                    {uploadAndUse ? 'Upload and use' : 'Upload'}
                  </Button>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </DialogBody>
        <DialogFooter>
          {many && (
            <span className="me-auto self-center text-xs text-muted-foreground">
              {picks.length} selected
            </span>
          )}
          <Button variant="outline" onClick={onCancel}>
            {selecting || many ? 'Cancel' : closeLabel}
          </Button>
          {selecting && (
            <Button onClick={() => onDone(selection)}>Done</Button>
          )}
          {many && (
            <Button disabled={picks.length === 0} onClick={() => onPickMany(picks)}>
              Done
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The selectable-tile tick of the catalogue picker (`dealer-kit/components/TileGrid.tsx`). */
function PickTick({ picked }: { picked: boolean }) {
  return (
    <span
      className={cn(
        'absolute end-1 top-1 z-10 flex size-5 items-center justify-center rounded-full border',
        picked
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-background/90 text-transparent',
      )}
      aria-hidden
    >
      <Check className="size-3" />
    </span>
  );
}
