'use client';

import { useMemo, useState } from 'react';
import { Container, Eye, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { useStockListApplied, useSupplierStockListFile } from '../../hooks/useFulfilment';
import { getFulfilmentSuppliers } from '../../services/fulfilmentService';
import { StockListUploadDialog } from './StockListUploadDialog';
import { UnmatchedSupplierCodesPanel } from './UnmatchedSupplierCodesPanel';
import { ContainerRequestSection } from './ContainerRequestSection';

/**
 * Ms Tee's screen: what to ask a supplier for on the next container.
 *
 * The order of the page IS the journey. Pick the supplier, optionally narrow to a date, and
 * the ranked request table (`ContainerRequestSection`) does the rest - nothing is asked that
 * can be derived, since the quantities, the ranking, and what the supplier is already holding
 * unfinished all come out of what is already on file. The only decisions left to her are the
 * supplier, any quantity she wants to override, and Send.
 *
 * The CBM-fit half of this page (container size, packed-stock fill tiles, and the resulting
 * loading plan) was cut on the captain's 20 Aug live-test ruling ("don't need stage 2"). It is
 * a UI-only removal: `SupplierNoticePanel` (tied to the loading-plan id that half produced) is
 * still in the tree but unreferenced from here, and the backend it read from
 * (`loading_plan_service`, the plan endpoints, supplier notices) is untouched - restoring it is
 * a revert of this component, not a rebuild.
 */

export function LoadingPlanView() {
  const [supplierId, setSupplierId] = useState('');
  // The picked option's own label, alongside the id - server-searched (below), so the
  // screen's title and every downstream string cannot assume the chosen supplier sits in
  // whatever unfiltered first page happens to be cached (S8-followup, same fix as the
  // proforma upload dialog: a supplier past the `/select` endpoint's 100-row cap is otherwise
  // unreachable by typing its name here).
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(null);
  // "Plan until" (captain, 20 Aug): an empty string means no cutoff, today's behaviour - every
  // open SO need counts regardless of date. Threaded straight to `ContainerRequestSection`, the
  // only place that reads it.
  const [planHorizonDate, setPlanHorizonDate] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [stockListPreviewOpen, setStockListPreviewOpen] = useState(false);

  const stockListFile = useSupplierStockListFile(supplierId || null);
  const invalidateSupplier = useStockListApplied();

  const supplierName = supplierOption?.label ?? 'this supplier';

  // The uploaded sheet itself, previewed through the same modal Resource Management uses.
  // `url` is left blank - it is a same-origin attachment id, not a public CDN link, and the
  // Excel slide reads bytes via `downloadUrl` regardless.
  const stockListPreviewItems = useMemo<AttachmentPreviewItem[]>(() => {
    const id = stockListFile.data?.attachment_id;
    if (!id) return [];
    return [
      {
        id,
        name: stockListFile.data?.filename || 'Stock list',
        url: '',
        downloadUrl: `/api/v1/resource-management/attachments/${id}/download`,
      },
    ];
  }, [stockListFile.data]);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 grow">
            <Label htmlFor="loading-plan-supplier" className="text-xs">
              Supplier
            </Label>
            <SearchableSelect
              id="loading-plan-supplier"
              value={supplierId}
              onChange={setSupplierId}
              onOptionChange={setSupplierOption}
              // Server-searched (S8-followup): the `/select` endpoint ilikes code + name and
              // caps at 100 rows, so a client-filtered static list silently hid any supplier
              // past that page. `fetchOptions` re-queries as the user types (debounced by
              // `SearchableSelect` itself).
              fetchOptions={(query) => getFulfilmentSuppliers(query)}
              selectedOption={supplierOption ?? undefined}
              placeholder="Choose a supplier"
              className="mt-1 w-full sm:w-80"
            />
          </div>
          <div>
            <Label htmlFor="loading-plan-horizon" className="text-xs">
              Plan until
            </Label>
            <Input
              id="loading-plan-horizon"
              type="date"
              className="mt-1 w-40"
              value={planHorizonDate}
              onChange={(e) => setPlanHorizonDate(e.target.value)}
            />
          </div>
          <div className="flex shrink-0 gap-2">
            {stockListFile.data?.attachment_id ? (
              <Button variant="outline" onClick={() => setStockListPreviewOpen(true)}>
                <Eye className="size-4" />
                View uploaded list
              </Button>
            ) : null}
            <Button
              variant="outline"
              onClick={() => setUploadOpen(true)}
              disabled={!supplierId}
              data-testid="open-stock-upload"
            >
              <Upload className="size-4" />
              Upload stock list
            </Button>
          </div>
        </div>
      </Card>

      {!supplierId ? (
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Container className="size-5" />
          </span>
          <p className="text-sm font-medium">Choose a supplier to plan a container.</p>
          <p className="text-2xs text-muted-foreground">
            The plan is built from their stock list and your open purchase orders with them.
          </p>
        </Card>
      ) : (
        <>
        {/* The queue of codes this supplier's file names and our catalogue does not - the
            stock behind them is invisible to the plan below until somebody answers them. */}
        <UnmatchedSupplierCodesPanel supplierId={supplierId} />
        <ContainerRequestSection
          supplierId={supplierId}
          supplierName={supplierName}
          planHorizonDate={planHorizonDate || null}
          onUploadStockList={() => setUploadOpen(true)}
        />
        </>
      )}

      {supplierId ? (
        <StockListUploadDialog
          open={uploadOpen}
          onOpenChange={setUploadOpen}
          supplierId={supplierId}
          supplierName={supplierName}
          onApplied={() => invalidateSupplier(supplierId)}
        />
      ) : null}

      <AttachmentPreviewModal
        open={stockListPreviewOpen}
        onOpenChange={setStockListPreviewOpen}
        items={stockListPreviewItems}
      />
    </div>
  );
}

export default LoadingPlanView;
