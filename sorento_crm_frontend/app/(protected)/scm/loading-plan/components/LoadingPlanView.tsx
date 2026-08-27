'use client';

import { useMemo, useState } from 'react';
import { Container, Eye, RefreshCw, Settings, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { type SearchableSelectOption } from '@/components/common/SearchableSelect';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { useStockListApplied, useSupplierStockListFile } from '../../hooks/useFulfilment';
import { useRematchSupplierCodes } from '../../hooks/useSupplierCodeAliases';
import { EM_DASH, fmtDate } from '../../lib/format';
import { UnmatchedSupplierCodesPanel } from './UnmatchedSupplierCodesPanel';
import { ContainerRequestSection } from './ContainerRequestSection';
import {
  PlanContainerDialog,
  type PlanContainerSelection,
  type PlanDocumentKind,
} from './PlanContainerDialog';

/**
 * Ms Tee's screen: what to ask a supplier for on the next container.
 *
 * The order of the page IS the journey. Pick the supplier, optionally narrow to a date, and
 * the ranked request table (`ContainerRequestSection`) does the rest - nothing is asked that
 * can be derived, since the quantities, the ranking, and what the supplier is already holding
 * unfinished all come out of what is already on file. The only decisions left to her are the
 * supplier, any quantity she wants to override, and Send.
 *
 * Those first two picks moved OFF this toolbar and into the Upload popup
 * (`PlanContainerDialog`, captain 27 Aug): one blue CTA starts the whole thing, and what was
 * chosen reads back as text, because a row of four controls made "plan a container" look like
 * four unrelated errands. What is left up here is the state (who, until when) and a gear for
 * the things done occasionally rather than every visit.
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
  // The picked option's own label, alongside the id - server-searched (in the popup), so the
  // screen's title and every downstream string cannot assume the chosen supplier sits in
  // whatever unfiltered first page happens to be cached (S8-followup, same fix as the
  // proforma upload dialog: a supplier past the `/select` endpoint's 100-row cap is otherwise
  // unreachable by typing its name here).
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(null);
  // "Plan until" (captain, 20 Aug): an empty string means no cutoff, today's behaviour - every
  // open SO need counts regardless of date. Threaded straight to `ContainerRequestSection`, the
  // only place that reads it.
  const [planHorizonDate, setPlanHorizonDate] = useState('');
  const [planOpen, setPlanOpen] = useState(false);
  // Null opens the popup on its first step; a document kind jumps straight to that upload,
  // for the CTAs that already know which document is being sent.
  const [planOpenTo, setPlanOpenTo] = useState<PlanDocumentKind | null>(null);
  const [stockListPreviewOpen, setStockListPreviewOpen] = useState(false);

  const stockListFile = useSupplierStockListFile(supplierId || null);
  const invalidateSupplier = useStockListApplied();
  // Same action `RefreshMatchingButton` runs on the queue panel - the panel hides itself when
  // every code binds, and that is exactly the state somebody is trying to reach after adding
  // the missing products (R18), so it is also reachable from up here.
  const rematch = useRematchSupplierCodes();

  const supplierName = supplierOption?.label ?? 'this supplier';

  const openPlanDialog = (to: PlanDocumentKind | null) => {
    setPlanOpenTo(to);
    setPlanOpen(true);
  };

  const applyPlanSelection = (selection: PlanContainerSelection) => {
    setSupplierId(selection.supplierId);
    setSupplierOption(selection.supplierOption);
    setPlanHorizonDate(selection.planHorizonDate);
    if (selection.supplierId) invalidateSupplier(selection.supplierId);
  };

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

  // The one CTA, in both places it has to be reachable from: the toolbar, and the empty
  // state where it is the only thing to do. Same action, so same wording and same weight.
  const uploadCta = (testId: string) => (
    <Button onClick={() => openPlanDialog(null)} data-testid={testId}>
      <Upload className="size-4" />
      Upload
    </Button>
  );

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-0.5">
            <p className="truncate text-sm" data-testid="plan-supplier-text">
              <span className="text-muted-foreground">Supplier: </span>
              <span className="font-medium">
                {supplierId ? supplierName : 'No supplier chosen'}
              </span>
            </p>
            <p className="text-xs" data-testid="plan-horizon-text">
              <span className="text-muted-foreground">Plan until: </span>
              <span className="font-medium">
                {planHorizonDate ? fmtDate(planHorizonDate) : EM_DASH}
              </span>
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {uploadCta('open-plan-container')}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="More actions"
                  disabled={!supplierId}
                  data-testid="loading-plan-more"
                >
                  <Settings className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                {stockListFile.data?.attachment_id ? (
                  <DropdownMenuItem onSelect={() => setStockListPreviewOpen(true)}>
                    <Eye className="size-4" />
                    View uploaded list
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem
                  disabled={rematch.isPending}
                  onSelect={() => rematch.mutate({ supplier_id: supplierId })}
                  data-testid="refresh-matching-item"
                >
                  <RefreshCw className="size-4" />
                  Refresh matching
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => openPlanDialog(null)}>
                  <Container className="size-4" />
                  Change supplier / plan until
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </Card>

      {!supplierId ? (
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Container className="size-5" />
          </span>
          <p className="text-sm font-medium">Choose a supplier to plan a container.</p>
          {uploadCta('open-plan-container-empty')}
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
          onUploadStockList={() => openPlanDialog('stock-list')}
          onUploadProforma={() => openPlanDialog('proforma')}
        />
        </>
      )}

      <PlanContainerDialog
        open={planOpen}
        onOpenChange={setPlanOpen}
        supplierId={supplierId}
        supplierOption={supplierOption}
        planHorizonDate={planHorizonDate}
        openTo={planOpenTo}
        onApply={applyPlanSelection}
      />

      <AttachmentPreviewModal
        open={stockListPreviewOpen}
        onOpenChange={setStockListPreviewOpen}
        items={stockListPreviewItems}
      />
    </div>
  );
}

export default LoadingPlanView;
