'use client';

/**
 * AIExtractFieldDialog - runs the AI extract pipeline against an
 * already-stored attachment, shows the suggested values per field, lets the
 * user drop bad guesses, and writes the kept values back to the product.
 *
 * Skips the file-upload stage of the portal-style ``AIExtractDialog`` because
 * the source doc is already on disk; lands directly on the review stage.
 *
 * For the composite "Dimensions" tooltip the parent passes
 * ``fieldKeys=['dimensions_length','dimensions_width','dimensions_height']``
 * so the review stage shows three rows from a single click.
 */
import { useEffect, useMemo, useState } from 'react';
import { Loader2, Sparkles, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { useUpdateProduct } from '../../hooks/useProducts';
import { useFieldLinkageSchema } from '../../hooks/useFieldLinkageSchema';

interface ExtractResult {
  values: Record<string, unknown>;
  per_field?: Record<string, { raw?: unknown; canonical?: unknown; source?: string }>;
  model?: string | null;
  provider?: string | null;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productId: string;
  /** UUID of the attachment to extract from. */
  attachmentId: string;
  /** Field keys this dialog should extract. e.g. ['weight'] or all three
   *  dimension keys for the composite Dimensions tooltip. */
  fieldKeys: string[];
}

export default function AIExtractFieldDialog({
  open,
  onOpenChange,
  productId,
  attachmentId,
  fieldKeys,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [discarded, setDiscarded] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const updateMutation = useUpdateProduct();
  const { data: schema } = useFieldLinkageSchema(open ? 'product' : null);

  const labelByKey = useMemo(() => {
    const out: Record<string, string> = {};
    for (const f of schema?.fields ?? []) out[f.name] = f.label;
    return out;
  }, [schema]);

  useEffect(() => {
    if (!open) {
      setResult(null);
      setDiscarded(new Set());
      setExtractError(null);
      setBusy(false);
      setSaving(false);
      return;
    }
    if (!attachmentId || fieldKeys.length === 0) return;
    let cancelled = false;
    (async () => {
      setBusy(true);
      setExtractError(null);
      try {
        const r = await apiFetch('/api/v1/master-data/ai-extract-field', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            attachment_id: attachmentId,
            entity_type: 'product',
            entity_id: productId,
            field_keys: fieldKeys,
          }),
        });
        if (!r.ok) {
          throw new Error(await extractApiError(r, 'AI extract failed.'));
        }
        const body = (await r.json()) as ExtractResult;
        if (!cancelled) {
          setResult(body);
          setDiscarded(new Set());
        }
      } catch (e) {
        if (!cancelled)
          setExtractError(
            e instanceof Error ? e.message : 'AI extract failed.',
          );
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, attachmentId, productId, fieldKeys]);

  const filled = useMemo(() => {
    if (!result) return [] as { name: string; label: string; value: unknown }[];
    const out: { name: string; label: string; value: unknown }[] = [];
    for (const key of fieldKeys) {
      const v = result.values?.[key];
      if (v === undefined || v === null || v === '') continue;
      out.push({
        name: key,
        label: labelByKey[key] ?? key,
        value: v,
      });
    }
    return out;
  }, [result, fieldKeys, labelByKey]);

  const kept = useMemo(
    () => filled.filter((f) => !discarded.has(f.name)),
    [filled, discarded],
  );

  const handleConfirm = async () => {
    if (kept.length === 0) {
      onOpenChange(false);
      return;
    }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      for (const f of kept) payload[f.name] = f.value;
      await updateMutation.mutateAsync({ id: productId, data: payload });
      toast.success(
        `Updated ${kept.length} field${kept.length === 1 ? '' : 's'} from AI Extract.`,
      );
      onOpenChange(false);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : 'Failed to apply AI Extract values.',
      );
    } finally {
      setSaving(false);
    }
  };

  const renderValue = (value: unknown): string => {
    if (Array.isArray(value)) return value.map(String).join(', ');
    if (typeof value === 'object' && value !== null) return JSON.stringify(value);
    return String(value);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="ai-extract-dialog"
        className="sm:max-w-lg"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            AI Extract
          </DialogTitle>
        </DialogHeader>

        {busy && (
          <div className="flex items-center gap-2 text-sm py-6">
            <Loader2 className="size-4 animate-spin" />
            Reading the document…
          </div>
        )}

        {extractError && !busy && (
          <p className="text-sm text-destructive py-4" data-testid="ai-extract-error">
            {extractError}
          </p>
        )}

        {!busy && !extractError && result && (
          <div data-testid="ai-extract-review" className="space-y-3 py-2">
            {filled.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                The model could not extract any of the requested fields from
                this document.
              </p>
            ) : (
              <ul className="space-y-2">
                {filled.map((f) => {
                  const dropped = discarded.has(f.name);
                  return (
                    <li
                      key={f.name}
                      className={`flex items-start justify-between gap-3 rounded-md border p-3 ${
                        dropped ? 'opacity-50 line-through' : ''
                      }`}
                      data-testid={`ai-extract-field-${f.name}`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-muted-foreground">{f.label}</p>
                        <p className="text-sm font-medium">
                          {renderValue(f.value)}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setDiscarded((prev) => {
                            const next = new Set(prev);
                            if (next.has(f.name)) next.delete(f.name);
                            else next.add(f.name);
                            return next;
                          })
                        }
                        data-testid={`ai-extract-drop-${f.name}`}
                      >
                        <X className="size-4" />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving || busy}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={busy || saving || kept.length === 0}
            data-testid="ai-extract-confirm"
          >
            {saving ? (
              <>
                <Loader2 className="size-4 animate-spin mr-2" />
                Applying…
              </>
            ) : (
              `Apply ${kept.length} value${kept.length === 1 ? '' : 's'}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
