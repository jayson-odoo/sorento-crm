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

import { useMemo, useState } from 'react';
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
  const linkedQuery = useTemplateProductIds(templateId, open);
  const linked = useMemo(() => linkedQuery.data ?? [], [linkedQuery.data]);
  const [show, setShow] = useState('');

  const { picked, grid } = useProductTargetPicker({
    initialSelection: linkedQuery.data,
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

  const save = async () => {
    const removing = removed;
    if (added.length > 0) {
      try {
        await link.mutateAsync(added);
      } catch {
        return; // the hook toasts the failure; nothing is parked
      }
    }
    if (removing.length > 0) {
      removal.start({ product_ids: removing });
      return; // the countdown replaces Save; the dialog closes once it commits
    }
    toast.success(`Linked ${plural(added.length, 'product')}`);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !link.isPending && onOpenChange(next)}>
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
            {linkedQuery.isLoading
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
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={link.isPending}>
                Cancel
              </Button>
              <Button
                onClick={() => void save()}
                disabled={busy || unchanged || overCap || linkedQuery.isLoading}
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
