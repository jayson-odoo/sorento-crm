'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
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
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
import {
  applyBulkAccessLevels,
  previewBulkAccessLevels,
  type AccessPropagationTarget,
} from '../../attachments/services/attachmentService';

export type BulkAccessLevelsScope =
  | { directoryId: string }
  | { attachmentIds: string[] }
  | null;

function kindLabel(kind: AccessPropagationTarget['kind']): string {
  switch (kind) {
    case 'product':
      return 'Product';
    case 'promotion':
      return 'Promotion';
    case 'form':
      return 'Marketing form';
    case 'packing_list':
      return 'Packing list';
    default:
      return kind;
  }
}

interface BulkAttachmentAccessLevelsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope: BulkAccessLevelsScope;
  onSuccess?: () => void;
}

export default function BulkAttachmentAccessLevelsDialog({
  open,
  onOpenChange,
  scope,
  onSuccess,
}: BulkAttachmentAccessLevelsDialogProps) {
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const defaultAccessLevels = accessTypeOptions.length > 0 ? accessTypeOptions.map((o) => o.code) : ['dealer', 'end_user'];

  const [accessLevels, setAccessLevels] = useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [attachmentCount, setAttachmentCount] = useState(0);
  const [targets, setTargets] = useState<AccessPropagationTarget[]>([]);
  const [propagateToLinked, setPropagateToLinked] = useState(true);
  const [applying, setApplying] = useState(false);

  const resetState = useCallback(() => {
    setAccessLevels([]);
    setPreviewLoading(false);
    setPreviewError(null);
    setAttachmentCount(0);
    setTargets([]);
    setPropagateToLinked(true);
    setApplying(false);
  }, []);

  useEffect(() => {
    if (!open || !scope) {
      resetState();
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    setTargets([]);
    setAttachmentCount(0);

    const body =
      'directoryId' in scope
        ? { directory_id: scope.directoryId }
        : { attachment_ids: scope.attachmentIds };

    previewBulkAccessLevels(body)
      .then((res) => {
        if (cancelled) return;
        setAttachmentCount(res.attachment_count);
        setTargets(res.targets ?? []);
        setPropagateToLinked((res.targets ?? []).length > 0);
        setAccessLevels(defaultAccessLevels);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setPreviewError(e instanceof Error ? e.message : 'Failed to load preview');
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, scope, resetState]);

  const handleApply = async () => {
    if (!scope || accessLevels.length === 0) {
      toast.error('Select at least one access level');
      return;
    }
    if (attachmentCount === 0) {
      toast.error('No attachments in scope');
      return;
    }
    setApplying(true);
    try {
      const bodyBase =
        'directoryId' in scope
          ? { directory_id: scope.directoryId }
          : { attachment_ids: scope.attachmentIds };
      await applyBulkAccessLevels({
        ...bodyBase,
        access_levels: accessLevels,
        propagate_to_linked: targets.length > 0 ? propagateToLinked : false,
      });
      toast.success('Access levels updated');
      onSuccess?.();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Adjust access levels</DialogTitle>
        </DialogHeader>

        {previewLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-6">
            <Loader2 className="size-4 animate-spin" />
            Loading…
          </div>
        )}

        {previewError && (
          <p className="text-sm text-destructive py-2" role="alert">
            {previewError}
          </p>
        )}

        {!previewLoading && !previewError && scope && (
          <div className="space-y-4 py-1">
            <p className="text-sm text-muted-foreground">
              {attachmentCount === 0
                ? 'There are no attachments in this scope.'
                : `This will update ${attachmentCount} attachment${attachmentCount === 1 ? '' : 's'}.`}
            </p>

            <div className="space-y-2">
              <Label>Access levels</Label>
              <div className="flex flex-wrap gap-4">
                {accessTypeOptions.map((opt) => {
                  const checked = accessLevels.includes(opt.code);
                  return (
                    <label key={opt.code} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(value) => {
                          const next = new Set(accessLevels);
                          if (value) next.add(opt.code);
                          else next.delete(opt.code);
                          setAccessLevels(Array.from(next));
                        }}
                      />
                      {opt.name || opt.code}
                    </label>
                  );
                })}
              </div>
            </div>

            {targets.length > 0 && (
              <div className="space-y-2 rounded-md border bg-muted/30 p-3">
                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <Checkbox
                    className="mt-0.5"
                    checked={propagateToLinked}
                    onCheckedChange={(v) => setPropagateToLinked(!!v)}
                  />
                  <span>
                    Propagate the same access levels to linked records listed below.
                  </span>
                </label>
                <div className="max-h-[min(16rem,45vh)] overflow-y-auto overscroll-contain rounded-sm border border-border/50 bg-background/80 py-2 pl-2 pr-1 [scrollbar-gutter:stable]">
                  <ul className="space-y-1.5 text-sm">
                    {targets.map((t) => (
                      <li key={`${t.kind}-${t.entity_id}`}>
                        <span className="text-muted-foreground">{kindLabel(t.kind)}</span>{' '}
                        <span className="font-medium tabular-nums">{t.code}</span>
                        {t.name ? <span className="text-muted-foreground"> - {t.name}</span> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleApply}
            disabled={
              applying ||
              previewLoading ||
              !!previewError ||
              !scope ||
              attachmentCount === 0 ||
              accessLevels.length === 0
            }
          >
            {applying ? (
              <>
                <Loader2 className="size-4 animate-spin mr-2" />
                Applying…
              </>
            ) : (
              'Apply'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
