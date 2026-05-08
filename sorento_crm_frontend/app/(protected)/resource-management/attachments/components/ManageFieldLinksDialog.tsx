'use client';

/**
 * ManageFieldLinksDialog — small modal opened from per-row actions in:
 *   - Product Attachments tab (attachment row in product detail)
 *   - AttachmentDetailModal Linkages tabs (each linked product row)
 *
 * Lets the user pick which product fields the attachment answers. Submits to
 * POST /api/v1/master-data/products/{product_id}/attachments/{attachment_id}/field-links.
 */
import { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
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
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  groupFieldSpecs,
  useFieldLinkageSchema,
} from '@/app/(protected)/master-data-management/products/hooks/useFieldLinkageSchema';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productId: string;
  attachmentId: string;
  /** Currently linked field keys for this attachment + product. When omitted,
   *  the dialog GETs them from the backend on open. */
  initialFieldKeys?: string[];
  onSaved?: (fieldKeys: string[]) => void;
}

export default function ManageFieldLinksDialog({
  open,
  onOpenChange,
  productId,
  attachmentId,
  initialFieldKeys,
  onSaved,
}: Props) {
  const { data: schema, isLoading } = useFieldLinkageSchema(open ? 'product' : null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (initialFieldKeys) {
      setSelected(new Set(initialFieldKeys));
      return;
    }
    // Fetch existing field keys when caller didn't pre-load them (e.g. when
    // opened from AttachmentDetailModal Linkages tab).
    let cancelled = false;
    (async () => {
      try {
        const r = await apiFetch(
          `/api/v1/master-data/products/${productId}/attachments/${attachmentId}/field-links`,
        );
        if (!r.ok) return;
        const body = await r.json();
        if (!cancelled) {
          setSelected(new Set((body.field_keys ?? []) as string[]));
        }
      } catch {
        // Best-effort; user can still pick fresh.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, initialFieldKeys, productId, attachmentId]);

  const groups = useMemo(
    () => (schema ? groupFieldSpecs(schema.fields) : []),
    [schema],
  );

  const toggleKey = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleGroup = (groupKey: string, names: string[]) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const allSelected = names.every((n) => next.has(n));
      if (allSelected) {
        for (const n of names) next.delete(n);
      } else {
        for (const n of names) next.add(n);
      }
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const fieldKeys = Array.from(selected);
      const response = await apiFetch(
        `/api/v1/master-data/products/${productId}/attachments/${attachmentId}/field-links`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ field_keys: fieldKeys }),
        },
      );
      if (!response.ok) {
        throw new Error(
          await extractApiError(response, 'Failed to save field links'),
        );
      }
      const body = await response.json();
      toast.success('Field links updated.');
      onSaved?.(body.field_keys ?? fieldKeys);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save field links');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Manage field links</DialogTitle>
          <DialogDescription>
            Tag this attachment with the product fields it answers (e.g. weight,
            dimensions). The AI agent and the product detail tooltip use this to
            surface the doc inline next to the field.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2 max-h-[50vh] overflow-y-auto">
          {isLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading fields…
            </div>
          )}

          {!isLoading && groups.length === 0 && (
            <p className="text-sm text-muted-foreground">No fields registered.</p>
          )}

          {groups.map((group) => {
            const isComposite = group.specs.length > 1;
            const allSelected = group.specs.every((s) => selected.has(s.name));
            const someSelected = group.specs.some((s) => selected.has(s.name));
            return (
              <div key={group.groupKey} className="space-y-2">
                {isComposite ? (
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                      onCheckedChange={() =>
                        toggleGroup(
                          group.groupKey,
                          group.specs.map((s) => s.name),
                        )
                      }
                      data-testid={`field-link-group-${group.groupKey}`}
                    />
                    {group.label}
                  </label>
                ) : null}
                <div className={isComposite ? 'pl-6 space-y-2' : 'space-y-2'}>
                  {group.specs.map((spec) => (
                    <label
                      key={spec.name}
                      className="flex items-center gap-2 text-sm"
                    >
                      <Checkbox
                        checked={selected.has(spec.name)}
                        onCheckedChange={() => toggleKey(spec.name)}
                        data-testid={`field-link-key-${spec.name}`}
                      />
                      <span>{spec.label}</span>
                      {spec.unit && (
                        <span className="text-xs text-muted-foreground">
                          ({spec.unit})
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving} data-testid="manage-field-links-save">
            {saving ? (
              <>
                <Loader2 className="size-4 animate-spin mr-2" />
                Saving…
              </>
            ) : (
              'Save'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
