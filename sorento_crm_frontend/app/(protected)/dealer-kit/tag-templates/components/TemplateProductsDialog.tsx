'use client';

/**
 * The designer's "Products" dialog (PRICETAG-TEMPLATE-PRODUCTS, mock v3, owner approved 10 Nov).
 *
 * One view on the shared product picker (`useProductTargetPicker`, the grid behind "Copy to other
 * products"): a tick means "uses this template". It opens with the template's products ticked;
 * ticking adds, unticking removes, and one Save applies both. Adds commit at once; removals are an
 * unlink, so they park with the standard countdown in place of the Save button (D7, no confirm).
 * Bulk link never changes an existing default (`bulk_assign`'s rule, server side).
 *
 * Owner hand test 11 Nov: combos too, in the same view. A "Type" filter swaps the grid's rows to
 * combos (the combo page's own `combo_tag_template` rows); a combo the template cannot print is
 * shown but cannot be ticked, with the reason on its checkbox. Combo ids carry a `combo:` prefix in
 * the shared selection so one tick set holds both.
 *
 * The parent mounts it only while open, so every open starts from a fresh seed.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
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
import type { GetProductsParams } from '@/app/(protected)/master-data-management/products/services/productService';
import type {
  Product,
  ProductApiResponse,
} from '@/app/(protected)/master-data-management/products/types/product.types';
import {
  templateComboIdsKey,
  templateProductIdsKey,
  useLinkTemplateProducts,
  useTemplateComboIds,
  useTemplateProductIds,
} from '../../hooks/useProductTagTemplates';
import { listTemplateCombos } from '../../services/productTagTemplateService';

const SHOW_LINKED = 'linked';
const COMBO = 'combo:';

type Kind = 'product' | 'combo';

/** A combo row, shaped as the picker's product row. */
type ComboRow = Product & { comboFitReason: string | null; isCombo: true };

const isComboId = (id: string) => id.startsWith(COMBO);
const comboId = (id: string) => id.slice(COMBO.length);

function comboFitReason(row: Product): string | undefined {
  return (row as Partial<ComboRow>).comboFitReason ?? undefined;
}

function rowHint(row: Product): string | undefined {
  if ((row as Partial<ComboRow>).isCombo) return 'Combo';
  return row.is_discontinued ? 'Discontinued' : undefined;
}

/** The footer: how many use the template now, or after Save with the change spelled out. */
export function templateProductsLine(after: number, added: number, removed: number): string {
  const uses = `${after.toLocaleString('en-US')} use this template`;
  if (added === 0 && removed === 0) return uses;
  return `${uses} after Save: ${added.toLocaleString('en-US')} added, ${removed.toLocaleString('en-US')} removed`;
}

function linkedLine(products: number, combos: number): string {
  return [
    products ? plural(products, 'product') : '',
    combos ? plural(combos, 'combo') : '',
  ]
    .filter(Boolean)
    .join(' and ');
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateId: string;
  templateName: string;
}

export function TemplateProductsDialog({ open, onOpenChange, templateId, templateName }: Props) {
  const productsQuery = useTemplateProductIds(templateId, open, { fresh: true });
  const combosQuery = useTemplateComboIds(templateId, open, { fresh: true });
  // The Save diffs against the links as they were when the dialog opened (frozen from fetches
  // made after mount, never a cached list), moved on only by this dialog's own adds. A link
  // made elsewhere meanwhile is then neither a phantom removal nor a phantom add.
  const [baseline, setBaseline] = useState<string[] | null>(null);
  useEffect(() => {
    if (
      baseline === null &&
      productsQuery.isFetchedAfterMount &&
      productsQuery.data &&
      combosQuery.isFetchedAfterMount &&
      combosQuery.data
    ) {
      setBaseline([...productsQuery.data, ...combosQuery.data.map((id) => `${COMBO}${id}`)]);
    }
  }, [
    baseline,
    productsQuery.isFetchedAfterMount,
    productsQuery.data,
    combosQuery.isFetchedAfterMount,
    combosQuery.data,
  ]);
  const linked = useMemo(() => baseline ?? [], [baseline]);
  const seedError = productsQuery.isError || combosQuery.isError;
  const loading = baseline === null && !seedError;
  const [show, setShow] = useState('');
  const [kind, setKind] = useState<Kind>('product');

  const fetchCombos = useCallback(
    async (params: GetProductsParams): Promise<ProductApiResponse> => {
      const res = await listTemplateCombos(templateId, {
        pageIndex: params.pageIndex,
        pageSize: params.pageSize,
        searchQuery: params.searchQuery,
        category_id: params.category_id,
        brand_id: params.brand_id,
        linkedOnly: Boolean(params.tag_template_id),
      });
      const data: ComboRow[] = res.data.map(
        (row) =>
          ({
            id: `${COMBO}${row.id}`,
            product_code: row.host_code,
            product_name: row.name,
            category: row.category_name ? { category_name: row.category_name } : undefined,
            brand: row.brand_name ? { brand_name: row.brand_name } : undefined,
            is_discontinued: false,
            comboFitReason: row.fit_reason,
            isCombo: true,
          }) as unknown as ComboRow,
      );
      return { data, pagination: res.pagination } as unknown as ProductApiResponse;
    },
    [templateId],
  );

  const { picked, grid } = useProductTargetPicker({
    initialSelection: baseline ?? undefined,
    extraParams: show === SHOW_LINKED ? { tag_template_id: templateId } : undefined,
    mergeSelectAll: true,
    fetchRows: kind === 'combo' ? fetchCombos : undefined,
    sourceKey: kind === 'combo' ? `template-combos:${templateId}` : 'products',
    rowDisabledReason: comboFitReason,
    rowHint,
    extraFilter: {
      activeCount: (show ? 1 : 0) + (kind === 'combo' ? 1 : 0),
      content: (
        <>
          <SearchableSelect
            value={kind}
            onChange={(value) => setKind(value === 'combo' ? 'combo' : 'product')}
            options={[
              { value: 'product', label: 'Products' },
              { value: 'combo', label: 'Combos' },
            ]}
            renderTriggerLabel={(opt) => <span className="block truncate">Type: {opt.label}</span>}
          />
          <SearchableSelect
            value={show}
            onChange={setShow}
            clearable
            options={[{ value: SHOW_LINKED, label: 'Uses this template' }]}
            placeholder="Show: all"
            renderTriggerLabel={(opt) => <span className="block truncate">Show: {opt.label}</span>}
          />
        </>
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
    subject: linkedLine(
      removed.filter((id) => !isComboId(id)).length,
      removed.filter(isComboId).length,
    ),
    surface: 'inline',
    successMessage: 'Products saved',
    invalidateKeys: [
      ['product-tag-templates'],
      ['combo-tag-templates'],
      templateProductIdsKey(templateId),
      templateComboIdsKey(templateId),
    ],
    onCommitted: () => onOpenChange(false),
  });

  const productOnly = (ids: string[]) => ids.filter((id) => !isComboId(id));
  const comboOnly = (ids: string[]) => ids.filter(isComboId).map(comboId);
  const overCap =
    productOnly(added).length > MAX_COPY_TARGETS ||
    comboOnly(added).length > MAX_COPY_TARGETS ||
    productOnly(removed).length > MAX_COPY_TARGETS ||
    comboOnly(removed).length > MAX_COPY_TARGETS;
  const busy = link.isPending || removal.isPending;
  const unchanged = added.length === 0 && removed.length === 0;
  const seedFailed = baseline === null && seedError;

  const save = async () => {
    const adding = added;
    const removing = removed;
    if (adding.length > 0) {
      let result: { changed: number; skipped?: number };
      try {
        result = await link.mutateAsync({
          productIds: productOnly(adding),
          comboIds: comboOnly(adding),
        });
      } catch {
        return; // the hook toasts the failure; nothing is parked
      }
      // Said now: a Cancel on the removals' countdown does not undo these.
      toast.success(`Linked ${linkedLine(productOnly(adding).length, comboOnly(adding).length)}`);
      if (result.skipped) {
        toast.error(`${plural(result.skipped, 'combo')} skipped: this template cannot print it`);
      }
      setBaseline((current) => [...(current ?? []), ...adding]);
    }
    if (removing.length > 0) {
      const productIds = productOnly(removing);
      const comboIds = comboOnly(removing);
      removal.start({
        ...(productIds.length ? { product_ids: productIds } : {}),
        ...(comboIds.length ? { combo_ids: comboIds } : {}),
      });
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
                  onClick={() => {
                    void productsQuery.refetch();
                    void combosQuery.refetch();
                  }}
                >
                  Retry
                </Button>
              </span>
            ) : loading
              ? 'Loading the products that use this template...'
              : overCap
                ? `One Save adds or removes at most ${MAX_COPY_TARGETS} products and ${MAX_COPY_TARGETS} combos.`
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
