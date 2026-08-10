'use client';

/**
 * AIExtractDialog — smart popup that prefills a portal submission form from
 * uploaded attachments (images + PDFs). Two stages:
 *
 *   1. Upload — local-only File[] buffer with drag/drop, file picker, and
 *      clipboard paste. Files are NOT uploaded to S3 yet; they're held in
 *      memory and shipped to /api/v1/public/portal/ai-extract on click.
 *   2. Review — read-only mirror of the FE field registry showing extracted
 *      values. Per-field × removes a guess. The user toggles the auto-attach
 *      checkbox and confirms; the parent merges values into empty form fields
 *      and (optionally) queues files for upload via the existing pendingFiles
 *      flow.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Clipboard, Loader2, Paperclip, Sparkles, Upload, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';

import {
  AI_EXTRACT_FORM_KEYS,
  AIExtractResult,
  PortalSubmissionKind,
  aiExtractFromFiles,
} from '../lib/portal-client';
import { canPreviewLocally, portalFetchBytes } from '../lib/portal-preview';

interface FieldDef {
  name: string;
  label: string;
  widget?: string;
}

export interface AIExtractApplyPayload {
  values: Record<string, string | string[]>;
  files: File[];
  alsoAttach: boolean;
  productLines: AIExtractResult['products'];
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: PortalSubmissionKind;
  fieldDefs: FieldDef[];
  onApply: (payload: AIExtractApplyPayload) => void;
}

type Stage = 'upload' | 'review';

const KINDS_WITH_LINE_ITEMS: PortalSubmissionKind[] = [
  'purchase_request',
  'sponsorship_form',
  'complaint',
];

export function AIExtractDialog({
  open,
  onOpenChange,
  kind,
  fieldDefs,
  onApply,
}: Props) {
  const [stage, setStage] = useState<Stage>('upload');
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [result, setResult] = useState<AIExtractResult | null>(null);
  const [discarded, setDiscarded] = useState<Set<string>>(new Set());
  const [alsoAttach, setAlsoAttach] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Blob: urls for the staged files, created and revoked in this one place so
  // they cannot leak. The rows below render from them and the shared modal
  // previews them in place - nothing here opens a new tab.
  const [stagedUrls, setStagedUrls] = useState<(string | null)[]>([]);
  useEffect(() => {
    const urls = files.map((f) => (canPreviewLocally(f) ? URL.createObjectURL(f) : null));
    setStagedUrls(urls);
    return () => {
      urls.forEach((u) => {
        if (u) URL.revokeObjectURL(u);
      });
    };
  }, [files]);

  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () =>
      files.map((file, idx) => ({
        id: `staged-${idx}-${file.name}`,
        name: file.name,
        url: stagedUrls[idx] ?? '',
        sizeBytes: file.size,
      })),
    [files, stagedUrls],
  );

  const openPreview = useCallback((index: number) => {
    setPreviewIndex(index);
    setPreviewOpen(true);
  }, []);

  const reset = useCallback(() => {
    setStage('upload');
    setFiles([]);
    setBusy(false);
    setExtractError(null);
    setResult(null);
    setDiscarded(new Set());
    setAlsoAttach(true);
    setPreviewOpen(false);
    setPreviewIndex(0);
  }, []);

  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  // Clipboard paste — only while open and on the upload stage.
  useEffect(() => {
    if (!open || stage !== 'upload') return;
    const onPaste = (e: ClipboardEvent) => {
      if (!e.clipboardData) return;
      const items = Array.from(e.clipboardData.items);
      const incoming: File[] = [];
      for (const item of items) {
        if (item.kind === 'file') {
          const f = item.getAsFile();
          if (f) incoming.push(f);
        }
      }
      // No file on the clipboard but there is text → save the paste as a .txt
      // file so it flows through the same upload/extract path.
      if (!incoming.length) {
        const text = e.clipboardData.getData('text/plain');
        if (text && text.trim()) {
          const ts = new Date().toISOString().replace(/[:.]/g, '-');
          incoming.push(new File([text], `pasted-${ts}.txt`, { type: 'text/plain' }));
        }
      }
      if (incoming.length) {
        e.preventDefault();
        setFiles((prev) => [...prev, ...incoming]);
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [open, stage]);

  const addFiles = useCallback((incoming: File[]) => {
    if (!incoming.length) return;
    setFiles((prev) => [...prev, ...incoming]);
  }, []);

  const removeFile = useCallback((idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const dropped = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
      addFiles(dropped);
    },
    [addFiles],
  );

  const handlePickClick = () => inputRef.current?.click();
  const handleSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files ? Array.from(e.target.files) : [];
    addFiles(picked);
    if (inputRef.current) inputRef.current.value = '';
  };

  // Mobile-friendly clipboard paste — `navigator.clipboard.read()` returns the
  // raw clipboard items including images (Cmd/Ctrl+V is desktop-only).
  const handlePasteFromClipboard = useCallback(async () => {
    const clip = (navigator as Navigator & {
      clipboard?: { read?: () => Promise<unknown> };
    }).clipboard;
    if (!clip || typeof clip.read !== 'function') {
      toast.error('Clipboard access not supported on this browser.');
      return;
    }
    try {
      const items = (await clip.read()) as unknown as Array<{
        types: string[];
        getType: (t: string) => Promise<Blob>;
      }>;
      const incoming: File[] = [];
      for (const item of items) {
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        const imageType = item.types.find((t) => t.startsWith('image/'));
        if (imageType) {
          const blob = await item.getType(imageType);
          const ext = imageType.split('/')[1] ?? 'png';
          incoming.push(new File([blob], `clipboard-${ts}.${ext}`, { type: imageType }));
          continue;
        }
        // No image — fall back to pasted text saved as a .txt file.
        if (item.types.includes('text/plain')) {
          const blob = await item.getType('text/plain');
          const text = (await blob.text()).trim();
          if (text) {
            incoming.push(new File([text], `pasted-${ts}.txt`, { type: 'text/plain' }));
          }
        }
      }
      if (incoming.length === 0) {
        toast.message('Clipboard has no image or text to paste.');
        return;
      }
      addFiles(incoming);
      toast.success(
        `Pasted ${incoming.length} item${incoming.length === 1 ? '' : 's'} from clipboard.`,
      );
    } catch (e) {
      toast.error(
        e instanceof Error
          ? e.message
          : 'Could not read clipboard. Allow clipboard access and try again.',
      );
    }
  }, [addFiles]);

  const handleExtract = async () => {
    if (!files.length) return;
    setBusy(true);
    setExtractError(null);
    try {
      const formKey = AI_EXTRACT_FORM_KEYS[kind];
      const r = await aiExtractFromFiles(formKey, files);
      setResult(r);
      setDiscarded(new Set());
      setStage('review');
    } catch (e) {
      setExtractError(e instanceof Error ? e.message : 'AI extract failed.');
    } finally {
      setBusy(false);
    }
  };

  const fieldsByName = useMemo(() => {
    const out: Record<string, FieldDef> = {};
    for (const f of fieldDefs) out[f.name] = f;
    return out;
  }, [fieldDefs]);

  const filledFieldEntries = useMemo(() => {
    if (!result) return [] as { name: string; label: string; value: string | string[] }[];
    const entries: { name: string; label: string; value: string | string[] }[] = [];
    for (const f of fieldDefs) {
      const v = result.values[f.name];
      if (v == null) continue;
      if (Array.isArray(v) && v.length === 0) continue;
      if (typeof v === 'string' && !v.trim()) continue;
      const value = Array.isArray(v) ? (v as string[]) : String(v);
      entries.push({ name: f.name, label: f.label, value });
    }
    return entries;
  }, [fieldDefs, result]);

  const remainingFieldEntries = useMemo(
    () => filledFieldEntries.filter((f) => !discarded.has(f.name)),
    [filledFieldEntries, discarded],
  );

  const handleConfirm = () => {
    if (!result) return;
    const out: Record<string, string | string[]> = {};
    for (const f of remainingFieldEntries) {
      out[f.name] = f.value;
    }
    onApply({
      values: out,
      files,
      alsoAttach,
      productLines: KINDS_WITH_LINE_ITEMS.includes(kind)
        ? (result.products ?? [])
        : [],
    });
    toast.success(
      `Applied ${remainingFieldEntries.length} field${remainingFieldEntries.length === 1 ? '' : 's'}.`,
    );
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="ai-extract-dialog"
        className="sm:max-w-2xl max-h-[85vh]"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            AI Extract
          </DialogTitle>
        </DialogHeader>

        {stage === 'upload' && (
          <>
            <div
              className="space-y-3 flex-1 min-h-0 overflow-y-auto -mx-1 px-1"
              data-testid="ai-extract-upload"
            >
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center transition ${
                  dragOver ? 'border-primary bg-primary/5' : 'border-border'
                }`}
                data-testid="ai-extract-dropzone"
              >
                <Upload className="h-6 w-6 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Drop files, paste (Ctrl/Cmd+V), or pick a source:
                </p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handlePickClick}
                    disabled={busy}
                  >
                    <Paperclip className="h-4 w-4 mr-2" />
                    Choose files
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handlePasteFromClipboard}
                    disabled={busy}
                    data-testid="ai-extract-paste-clipboard"
                  >
                    <Clipboard className="h-4 w-4 mr-2" />
                    Paste from clipboard
                  </Button>
                </div>
                <input
                  ref={inputRef}
                  type="file"
                  accept="image/*,video/*,.pdf,.txt"
                  className="hidden"
                  multiple
                  data-testid="ai-extract-file-input"
                  onChange={handleSelect}
                />
              </div>

              {files.length > 0 && (
                <ul
                  className="space-y-2"
                  data-testid="ai-extract-file-list"
                >
                  {files.map((file, idx) => (
                    <PendingPreview
                      key={`${file.name}-${idx}-${file.size}`}
                      file={file}
                      previewUrl={stagedUrls[idx] ?? null}
                      onView={() => openPreview(idx)}
                      onRemove={() => removeFile(idx)}
                    />
                  ))}
                </ul>
              )}

              {extractError && (
                <p className="text-sm text-destructive" data-testid="ai-extract-error">
                  {extractError}
                </p>
              )}
            </div>

            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={busy}
              >
                Cancel
              </Button>
              <Button
                onClick={handleExtract}
                disabled={busy || files.length === 0}
                data-testid="ai-extract-run"
              >
                {busy ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Reading {files.length} file{files.length === 1 ? '' : 's'}...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    AI Extract
                  </>
                )}
              </Button>
            </DialogFooter>
          </>
        )}

        {stage === 'review' && result && (
          <>
            <div
              className="space-y-3 flex-1 min-h-0 overflow-y-auto -mx-1 px-1"
              data-testid="ai-extract-review"
            >
              {remainingFieldEntries.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nothing extractable was found. Go back and try with clearer
                  pages, or close to fill the form manually.
                </p>
              ) : (
                <div className="rounded-md border border-border">
                  <table className="w-full text-sm">
                    <tbody>
                      {remainingFieldEntries.map((f) => (
                        <tr
                          key={f.name}
                          className="border-b border-border last:border-b-0"
                          data-testid={`ai-extract-field-${f.name}`}
                        >
                          <td className="px-3 py-2 align-top text-muted-foreground w-44">
                            {fieldsByName[f.name]?.label ?? f.label}
                          </td>
                          <td className="px-3 py-2 align-top">
                            <span className="break-words">
                              {Array.isArray(f.value) ? f.value.join(', ') : f.value}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right align-top w-12">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              aria-label={`Drop ${f.label}`}
                              data-testid={`ai-extract-drop-${f.name}`}
                              onClick={() =>
                                setDiscarded((prev) => {
                                  const next = new Set(prev);
                                  next.add(f.name);
                                  return next;
                                })
                              }
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {KINDS_WITH_LINE_ITEMS.includes(kind) && result.products && result.products.length > 0 && (
                <div className="rounded-md border border-border">
                  <div className="px-3 py-2 text-xs uppercase tracking-wide text-muted-foreground border-b border-border">
                    Line items ({result.products.length}) — will be applied to the items list
                  </div>
                  <table
                    className="w-full text-sm"
                    data-testid="ai-extract-products-table"
                  >
                    <thead className="text-xs text-muted-foreground">
                      <tr className="border-b border-border">
                        <th className="px-3 py-1.5 text-left font-normal">Product code</th>
                        <th className="px-3 py-1.5 text-right font-normal">Qty</th>
                        {kind !== 'complaint' && (
                          <>
                            <th className="px-3 py-1.5 text-right font-normal">Unit price</th>
                            <th className="px-3 py-1.5 text-right font-normal">Total</th>
                            <th className="px-3 py-1.5 text-left font-normal">Notes</th>
                          </>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {result.products.map((p, i) => (
                        <tr
                          key={i}
                          className="border-b border-border last:border-b-0"
                          data-testid={`ai-extract-product-row-${i}`}
                        >
                          <td className="px-3 py-2 align-top break-words">{p.product_code ?? '—'}</td>
                          <td className="px-3 py-2 align-top text-right">{p.quantity ?? '—'}</td>
                          {kind !== 'complaint' && (
                            <>
                              <td className="px-3 py-2 align-top text-right">{p.unit_price ?? '—'}</td>
                              <td className="px-3 py-2 align-top text-right">{p.total ?? '—'}</td>
                              <td className="px-3 py-2 align-top break-words">{p.notes ?? ''}</td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <Checkbox
                  id="ai-extract-also-attach"
                  checked={alsoAttach}
                  onCheckedChange={(v) => setAlsoAttach(v === true)}
                  data-testid="ai-extract-attach"
                />
                <Label htmlFor="ai-extract-also-attach" className="cursor-pointer">
                  Also attach these {files.length} file{files.length === 1 ? '' : 's'} to my{' '}
                  {kind === 'complaint' ? 'complaint' : 'submission'}
                </Label>
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setStage('upload');
                  setExtractError(null);
                }}
              >
                Back
              </Button>
              <Button
                onClick={handleConfirm}
                disabled={remainingFieldEntries.length === 0}
                data-testid="ai-extract-confirm"
              >
                Confirm and prefill
              </Button>
            </DialogFooter>
          </>
        )}

        <AttachmentPreviewModal
          open={previewOpen}
          onOpenChange={setPreviewOpen}
          items={previewItems}
          startIndex={previewIndex}
          fetchBytes={portalFetchBytes}
        />
      </DialogContent>
    </Dialog>
  );
}

function PendingPreview({
  file,
  previewUrl,
  onView,
  onRemove,
}: {
  file: File;
  /** blob: url owned by the dialog (created + revoked there), or null for a
   *  type the modal cannot render inline. */
  previewUrl: string | null;
  onView: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-md border border-border px-3 py-2">
      <div className="shrink-0">
        {previewUrl && file.type.startsWith('image/') ? (
          <button type="button" onClick={onView} aria-label={`Preview ${file.name}`}>
            <img
              src={previewUrl}
              alt={file.name}
              className="h-12 w-12 rounded object-cover border border-border"
            />
          </button>
        ) : previewUrl && file.type.startsWith('video/') ? (
          <button type="button" onClick={onView} aria-label={`Preview ${file.name}`}>
            <video
              src={previewUrl}
              muted
              playsInline
              preload="metadata"
              className="h-12 w-12 rounded object-cover border border-border"
            />
          </button>
        ) : previewUrl ? (
          <button type="button" onClick={onView} aria-label={`Preview ${file.name}`}>
            <FileThumb label="PDF" interactive />
          </button>
        ) : isTextFile(file.name, file.type) ? (
          <TextPreview name={file.name} loadText={() => file.text()}>
            <FileThumb label="TXT" interactive />
          </TextPreview>
        ) : (
          <FileThumb label="FILE" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={file.name}>
          {file.name}
        </p>
        <p className="text-xs text-muted-foreground">
          {(file.size / 1024).toFixed(1)} KB
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRemove}
        aria-label={`Remove ${file.name}`}
      >
        <X className="h-4 w-4" />
      </Button>
    </li>
  );
}

function isTextFile(name?: string | null, type?: string | null): boolean {
  if (type?.startsWith('text/')) return true;
  return /\.txt$/i.test(name ?? '');
}

function FileThumb({ label, interactive }: { label: string; interactive?: boolean }) {
  return (
    <div
      className={`h-12 w-12 rounded bg-muted flex items-center justify-center text-xs text-muted-foreground border border-border ${
        interactive ? 'cursor-pointer hover:bg-muted/70 transition' : ''
      }`}
    >
      {label}
    </div>
  );
}

function TextPreview({
  name,
  loadText,
  children,
}: {
  name: string;
  loadText: () => Promise<string>;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleOpen = useCallback(
    async (next: boolean) => {
      setOpen(next);
      if (next && content === null && error === null) {
        try {
          setContent(await loadText());
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Could not read file.');
        }
      }
    },
    [content, error, loadText],
  );

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <button
        type="button"
        onClick={() => handleOpen(true)}
        aria-label={`Preview ${name}`}
        className="block"
      >
        {children}
      </button>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="truncate" title={name}>
            {name}
          </DialogTitle>
        </DialogHeader>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : content === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 text-sm">
            {content || '(empty file)'}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}
