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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Paperclip, Sparkles, Upload, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';

import {
  AI_EXTRACT_FORM_KEYS,
  AIExtractResult,
  PortalSubmissionKind,
  aiExtractFromFiles,
} from '../lib/portal-client';

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

const PREVIEWABLE = /^image\//;

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
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setStage('upload');
    setFiles([]);
    setBusy(false);
    setExtractError(null);
    setResult(null);
    setDiscarded(new Set());
    setAlsoAttach(true);
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
      productLines: result.products ?? [],
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
        className="sm:max-w-2xl"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            AI Extract
          </DialogTitle>
          <DialogDescription>
            Drop the delivery order PDF, defect photos, or message screenshots —
            we&apos;ll read them and prefill this form. You review before anything
            is saved.
          </DialogDescription>
        </DialogHeader>

        {stage === 'upload' && (
          <div className="space-y-3" data-testid="ai-extract-upload">
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
                Drop files here, paste a screenshot (Ctrl/Cmd+V), or
              </p>
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
              <input
                ref={inputRef}
                type="file"
                accept="image/*,.pdf"
                className="hidden"
                multiple
                data-testid="ai-extract-file-input"
                onChange={handleSelect}
              />
            </div>

            {files.length > 0 && (
              <ul className="space-y-2" data-testid="ai-extract-file-list">
                {files.map((file, idx) => (
                  <PendingPreview
                    key={`${file.name}-${idx}-${file.size}`}
                    file={file}
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
          </div>
        )}

        {stage === 'review' && result && (
          <div className="space-y-3" data-testid="ai-extract-review">
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

            {result.products && result.products.length > 0 && (
              <div className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
                {result.products.length} line item{result.products.length === 1 ? '' : 's'} also detected (will be applied to the items list).
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

            {result.usage && result.usage.total_tokens > 0 && (
              <p className="text-xs text-muted-foreground">
                Used {result.usage.total_tokens} tokens
                {result.model ? ` · ${result.model}` : ''}.
              </p>
            )}

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
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PendingPreview({
  file,
  onRemove,
}: {
  file: File;
  onRemove: () => void;
}) {
  const previewUrl = useMemo(() => {
    if (!PREVIEWABLE.test(file.type)) return null;
    return URL.createObjectURL(file);
  }, [file]);
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);
  return (
    <li className="flex items-center gap-3 rounded-md border border-border px-3 py-2">
      <div className="shrink-0">
        {previewUrl ? (
          <img
            src={previewUrl}
            alt={file.name}
            className="h-12 w-12 rounded object-cover border border-border"
          />
        ) : (
          <div className="h-12 w-12 rounded bg-muted flex items-center justify-center text-xs text-muted-foreground">
            PDF
          </div>
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
