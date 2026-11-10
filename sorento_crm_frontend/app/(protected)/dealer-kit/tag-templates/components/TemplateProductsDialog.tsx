'use client';

/**
 * The designer's "Products" dialog (PRICETAG-TEMPLATE-PRODUCTS, mock v3, owner approved 10 Nov).
 *
 * One view on the shared product picker (`useProductTargetPicker`, the grid behind "Copy to other
 * products"): a tick means "uses this template". It opens with the template's products ticked;
 * ticking adds, unticking removes, and one Save applies both. Adds commit at once; removals are an
 * unlink, so they park with the standard countdown in place of the Save button (D7, no confirm).
 * Bulk link never changes a product's existing default (`bulk_assign`'s rule, server side).
 *
 * The parent mounts it only while open, so every open starts from a fresh seed.
 */

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { toast } from '@/lib/toast';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  MAX_COPY_TARGETS,
  plural,
  useProductTargetPicker,
} from '@/app/(protected)/master-data-management/products/[id]/components/ProductTargetPicker';
import {
  templateProductIdsKey,
  useLinkTemplateProducts,
  useTemplateProductIds,
} from '../../hooks/useProductTagTemplates';

const SHOW_LINKED = 'linked';

/** The footer: how many use the template now, or after Save with the change spelled out. */
export function templateProductsLine(after: number, added: number, removed: number): string {
  const uses = `${after.toLocaleString('en-US')} use this template`;
  if (added === 0 && removed === 0) return uses;
  return `${uses} after Save: ${added.toLocaleString('en-US')} added, ${removed.toLocaleString('en-US')} removed`;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateId: string;
  templateName: string;
}

export function TemplateProductsDialog({ open, onOpenChange, templateId, templateName }: Props) {
  const linkedQuery = useTemplateProductIds(templateId, open, { fresh: true });
  // The Save diffs against the links as they were when the dialog opened (frozen from a fetch
  // made after mount, never a cached list), moved on only by this dialog's own adds. A link
  // made elsewhere meanwhile is then neither a phantom removal nor a phantom add.
  const [baseline, setBaseline] = useState<string[] | null>(null);
  useEffect(() => {
    if (baseline === null && linkedQuery.isFetchedAfterMount && linkedQuery.data) {
      setBaseline(linkedQuery.data);
    }
  }, [baseline, linkedQuery.isFetchedAfterMount, linkedQuery.data]);
  const linked = useMemo(() => baseline ?? [], [baseline]);
  const loading = baseline === null && !linkedQuery.isError;
  const [show, setShow] = useState('');

  const { picked, grid } = useProductTargetPicker({
    initialSelection: baseline ?? undefined,
    extraParams: show === SHOW_LINKED ? { tag_template_id: templateId } : undefined,
    mergeSelectAll: true,
    extraFilter: {
      activeCount: show ? 1 : 0,
      content: (
        <SearchableSelect
          value={show}
          onChange={setShow}
          clearable
          options={[{ value: SHOW_LINKED, label: 'Uses this template' }]}
          placeholder="Show: all products"
          renderTriggerLabel={(opt) => <span className="block truncate">Show: {opt.label}</span>}
        />
      ),
    },
  });

  const { added, removed } = useMemo(() => {
    const now = new Set(picked);
    const before = new Set(linked);
    return {
      added: picked.filter((id) => !before.has(id)),
      removed: linked.filter((id) => !now.has(id)),
    };
  }, [picked, linked]);

  const link = useLinkTemplateProducts(templateId);
  const removal = useDeferredAction({
    actionKey: 'tag_template.unassign_products',
    entityType: 'tag_template',
    entityId: templateId,
    verb: 'Removing',
    subject: plural(removed.length, 'product'),
    surface: 'inline',
    successMessage: 'Products saved',
    invalidateKeys: [['product-tag-templates'], templateProductIdsKey(templateId)],
    onCommitted: () => onOpenChange(false),
  });

  const overCap = added.length > MAX_COPY_TARGETS || removed.length > MAX_COPY_TARGETS;
  const busy = link.isPending || removal.isPending;
  const unchanged = added.length === 0 && removed.length === 0;
  const seedFailed = baseline === null && linkedQuery.isError;

  const save = async () => {
    const adding = added;
    const removing = removed;
    if (adding.length > 0) {
      try {
        await link.mutateAsync(adding);
      } catch {
        return; // the hook toasts the failure; nothing is parked
      }
      // Said now: a Cancel on the removals' countdown does not undo these.
      toast.success(`Linked ${plural(adding.length, 'product')}`);
      setBaseline((current) => [...(current ?? []), ...adding]);
    }
    if (removing.length > 0) {
      removal.start({ product_ids: removing });
      return; // the countdown replaces Save; the dialog closes once it commits
    }
    onOpenChange(false);
  };

  return (
    // Not closable mid-Save: during the removals' countdown the dialog holds the only Cancel.
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="flex max-h-[90dvh] w-[calc(100vw-2rem)] max-w-5xl flex-col"
        aria-describedby={undefined}
      >
        <DialogHeader>
          {/* pe-8: clear of the close X at 375px. */}
          <DialogTitle className="pe-8 break-words">
            Products for{' '}
            <span className="inline-block max-w-full truncate align-bottom" title={templateName}>
              {templateName}
            </span>
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto">{grid}</DialogBody>
        <DialogFooter className="flex-wrap items-center gap-2">
          <span className="mr-auto text-sm text-muted-foreground" aria-live="polite">
            {seedFailed ? (
              <span className="text-destructive">
                Could not load the products that use this template.{' '}
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0"
                  onClick={() => void linkedQuery.refetch()}
                >
                  Retry
                </Button>
              </span>
            ) : loading
              ? 'Loading the products that use this template...'
              : overCap
                ? `One Save adds or removes at most ${MAX_COPY_TARGETS} products.`
                : templateProductsLine(
                    linked.length + added.length - removed.length,
                    added.length,
                    removed.length,
                  )}
          </span>
          {removal.countdown ?? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                Cancel
              </Button>
              <Button
                onClick={() => void save()}
                disabled={busy || unchanged || overCap || baseline === null}
              >
                {link.isPending ? <LoaderCircle className="mr-1 size-4 animate-spin" /> : null}
                Save
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default TemplateProductsDialog;
