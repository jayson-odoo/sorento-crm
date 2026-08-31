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
import { Loader2, Search, Upload } from 'lucide-react';
import { toast } from 'sonner';
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
import type { ImageSource, TagImage } from '@/lib/dealer-kit/tag-template-types';
import {
  listAssets,
  uploadAsset,
  type AssetKind,
  type KitAsset,
} from '../../services/assetService';

const LIBRARY_TAGS: { value: string; label: string }[] = [
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
  title?: string;
  onCancel: () => void;
  onPick: (source: ImageSource) => void;
}

export function AssetPickerDialog({
  open,
  productImages,
  allowProductPhotos = true,
  uploadKind = 'decorative',
  title = 'Choose an image',
  onCancel,
  onPick,
}: AssetPickerDialogProps) {
  const [tab, setTab] = useState(allowProductPhotos ? 'product' : 'library');
  const [assets, setAssets] = useState<KitAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [tagFilter, setTagFilter] = useState('__all__');
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listAssets({
        query,
        tag: tagFilter === '__all__' ? undefined : tagFilter,
        limit: 100,
      });
      setAssets(rows);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load artwork');
    } finally {
      setLoading(false);
    }
  }, [query, tagFilter]);

  useEffect(() => {
    if (!open) return;
    setTab(allowProductPhotos ? 'product' : 'library');
    setFiles([]);
  }, [open, allowProductPhotos]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const handleUpload = useCallback(async () => {
    const file = files[0];
    if (!file) return;
    setUploading(true);
    try {
      const asset = await uploadAsset({
        file,
        kind: uploadKind,
        tags: uploadKind === 'decorative' ? undefined : [uploadKind],
      });
      setFiles([]);
      toast.success(`${asset.name} added to the library`);
      onPick({ type: 'asset', assetId: asset.id });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }, [files, uploadKind, onPick]);

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
                    photos you can use. Bind the block to a product, or pick from
                    the asset library.
                  </p>
                ) : (
                  <div className="grid max-h-80 grid-cols-4 gap-2 overflow-auto">
                    {productImages.map((image) => (
                      <button
                        key={image.attachment_id}
                        type="button"
                        className="group relative aspect-square overflow-hidden rounded border hover:ring-2 hover:ring-primary"
                        onClick={() =>
                          onPick({
                            type: 'product_attachment',
                            attachmentId: image.attachment_id,
                          })
                        }
                      >
                        <img
                          src={image.url}
                          alt=""
                          className="size-full object-contain"
                        />
                        {image.is_primary && (
                          <span className="absolute left-1 top-1 rounded bg-primary px-1 text-[9px] text-primary-foreground">
                            Primary
                          </span>
                        )}
                      </button>
                    ))}
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
                <div className="w-40">
                  <SearchableSelect
                    value={tagFilter}
                    onChange={setTagFilter}
                    options={LIBRARY_TAGS}
                    size="sm"
                  />
                </div>
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
                  {assets.map((asset) => (
                    <button
                      key={asset.id}
                      type="button"
                      className="flex flex-col items-center gap-1 rounded border p-1 hover:ring-2 hover:ring-primary"
                      onClick={() => onPick({ type: 'asset', assetId: asset.id })}
                      title={asset.name}
                    >
                      <span className="flex aspect-square w-full items-center justify-center overflow-hidden">
                        {asset.url ? (
                                            <img
                            src={asset.url}
                            alt=""
                            className="size-full object-contain"
                          />
                        ) : (
                          <span className="text-[9px] text-muted-foreground">
                            No preview
                          </span>
                        )}
                      </span>
                      <span className="w-full truncate text-[10px]">{asset.name}</span>
                    </button>
                  ))}
                </div>
              )}

              <div className="flex flex-col gap-2 border-t pt-3">
                <FileDropzone
                  accept=".png,.jpg,.jpeg,.webp,.svg"
                  files={files}
                  onFilesChange={setFiles}
                  maxSizeMb={20}
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
                    Upload and use
                  </Button>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
