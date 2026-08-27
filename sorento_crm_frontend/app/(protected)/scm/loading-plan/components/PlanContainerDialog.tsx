'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { getFulfilmentSuppliers } from '../../services/fulfilmentService';
import { ProformaUploadDialog } from '../../proforma-invoices/components/ProformaUploadDialog';
import { StockListUploadDialog } from './StockListUploadDialog';

/**
 * One way onto the loading plan (captain, 27 Aug).
 *
 * The toolbar used to carry the supplier picker, the date, and one button per document, so
 * planning a container read as four unrelated controls that happened to sit on the same row.
 * It is one decision - "plan this supplier's next container, here is what they sent me" - so
 * it is one popup, and the two answers it needs first (whose container, how far ahead) are
 * asked once here rather than left as inputs on the page behind it.
 *
 * Two steps, because the second one already exists. Step 1 collects supplier + plan until +
 * which document; step 2 hands straight over to the SAME `StockListUploadDialog` /
 * `ProformaUploadDialog` used everywhere else, in fixed-supplier mode. Nothing about either
 * upload is reimplemented here.
 *
 * "Plan without a file" is the third answer: a supplier whose list or proforma is already on
 * file needs no upload at all, only the two picks, and forcing a file on that person is what
 * made the old toolbar's Upload buttons look mandatory.
 */

export type PlanDocumentKind = 'stock-list' | 'proforma';

export interface PlanContainerSelection {
  supplierId: string;
  supplierOption: SearchableSelectOption | null;
  planHorizonDate: string;
}

export function PlanContainerDialog({
  open,
  onOpenChange,
  supplierId: pageSupplierId,
  supplierOption: pageSupplierOption,
  planHorizonDate: pagePlanHorizonDate,
  openTo = null,
  onApply,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  /** What the page is planning right now - the starting point when the popup is re-opened
   *  to change it, and what a jump straight to step 2 uploads against. */
  supplierId: string;
  supplierOption: SearchableSelectOption | null;
  planHorizonDate: string;
  /** Opened from a CTA that already knows which document is being sent (the request
   *  section's own empty state), so step 1 is skipped. Null opens on step 1. */
  openTo?: PlanDocumentKind | null;
  /** Fired when the picks become the page's: on "Plan without a file", and after either
   *  upload applies, so the build re-reads against the supplier just uploaded for. */
  onApply: (selection: PlanContainerSelection) => void;
}) {
  // Held here, not lifted: the page only learns the picks once they are applied, so a
  // Cancel on step 2 cannot leave the plan behind the popup pointing at a supplier nobody
  // confirmed. Deliberately NOT reset on close - re-opening lands on the last answers,
  // since the usual second visit is "same supplier, other document".
  const [supplierId, setSupplierId] = useState(pageSupplierId);
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(
    pageSupplierOption,
  );
  const [planHorizonDate, setPlanHorizonDate] = useState(pagePlanHorizonDate);
  const [docKind, setDocKind] = useState<PlanDocumentKind>('stock-list');
  const [step, setStep] = useState<'choose' | 'upload'>('choose');

  // What the page is planning, readable without being a dependency of the effect below.
  // It changes the moment an upload applies, and a step-2 dialog that re-ran its own setup
  // on that change would throw the operator back to step 1 on top of their own result.
  const pageSelection = useRef<PlanContainerSelection>({
    supplierId: pageSupplierId,
    supplierOption: pageSupplierOption,
    planHorizonDate: pagePlanHorizonDate,
  });
  useEffect(() => {
    pageSelection.current = {
      supplierId: pageSupplierId,
      supplierOption: pageSupplierOption,
      planHorizonDate: pagePlanHorizonDate,
    };
  });

  useEffect(() => {
    if (!open) return;
    if (openTo) {
      // The caller knows both the supplier and the document, so the popup carries them
      // rather than asking again for what is already on screen behind it.
      setDocKind(openTo);
      setSupplierId(pageSelection.current.supplierId);
      setSupplierOption(pageSelection.current.supplierOption);
      setPlanHorizonDate(pageSelection.current.planHorizonDate);
      setStep('upload');
      return;
    }
    setStep('choose');
  }, [open, openTo]);

  const selection = (): PlanContainerSelection => ({
    supplierId,
    supplierOption,
    planHorizonDate,
  });

  const supplierName = supplierOption?.label ?? 'this supplier';

  if (step === 'upload' && supplierId) {
    const handleApplied = () => onApply(selection());
    // The upload dialog stays open on its own result summary (what was written, what it
    // replaced, which invoices were named) - that is the answer to the Confirm, and closing
    // over it is how an apply reads as a no-op. The plan behind it has already re-read.
    const handleOpenChange = (next: boolean) => {
      if (!next) setStep('choose');
      onOpenChange(next);
    };

    return docKind === 'proforma' ? (
      <ProformaUploadDialog
        open={open}
        onOpenChange={handleOpenChange}
        supplierId={supplierId}
        supplierOption={supplierOption}
        onApplied={handleApplied}
      />
    ) : (
      <StockListUploadDialog
        open={open}
        onOpenChange={handleOpenChange}
        supplierId={supplierId}
        supplierName={supplierName}
        onApplied={handleApplied}
      />
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Plan a container</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div>
            <Label htmlFor="plan-container-supplier" className="mb-1 block text-xs">
              Supplier
            </Label>
            <SearchableSelect
              id="plan-container-supplier"
              value={supplierId}
              onChange={setSupplierId}
              onOptionChange={setSupplierOption}
              // Server-searched, as on every other supplier picker in SCM: the `/select`
              // endpoint ilikes code + name and caps at 100 rows, so a client-filtered
              // static list silently hides anyone past that page.
              fetchOptions={(query) => getFulfilmentSuppliers(query)}
              selectedOption={supplierOption ?? undefined}
              placeholder="Choose a supplier"
              className="w-full"
            />
          </div>

          <div>
            <Label htmlFor="plan-container-horizon" className="mb-1 block text-xs">
              Plan until
            </Label>
            <div className="flex items-center gap-2">
              <Input
                id="plan-container-horizon"
                type="date"
                className="w-44"
                value={planHorizonDate}
                onChange={(e) => setPlanHorizonDate(e.target.value)}
              />
              {planHorizonDate ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPlanHorizonDate('')}
                  data-testid="clear-plan-horizon"
                >
                  Clear
                </Button>
              ) : null}
            </div>
          </div>

          <div>
            <Label className="mb-1 block text-xs">Document</Label>
            <RadioGroup
              value={docKind}
              onValueChange={(next) => setDocKind(next as PlanDocumentKind)}
              className="grid-cols-1 sm:grid-cols-2"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="stock-list" id="plan-container-doc-stock" />
                <Label htmlFor="plan-container-doc-stock" className="text-sm font-normal">
                  Stock list
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="proforma" id="plan-container-doc-proforma" />
                <Label htmlFor="plan-container-doc-proforma" className="text-sm font-normal">
                  Proforma invoice
                </Label>
              </div>
            </RadioGroup>
          </div>
        </DialogBody>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="outline"
            disabled={!supplierId}
            onClick={() => {
              onApply(selection());
              onOpenChange(false);
            }}
            data-testid="plan-without-file"
          >
            Plan without a file
          </Button>
          <Button
            disabled={!supplierId}
            onClick={() => setStep('upload')}
            data-testid="plan-container-continue"
          >
            Continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PlanContainerDialog;
