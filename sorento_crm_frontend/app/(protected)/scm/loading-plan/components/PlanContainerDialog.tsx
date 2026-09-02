'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircle, TestTube } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { MAX_SIZE_MB, useTwoStepUpload } from '../../reorder/hooks/useTwoStepUpload';
import { CountTile } from '../../reorder/components/UploadCountTile';
import { UploadTestVerdict, type UploadTestResult } from '../../reorder/components/UploadTestVerdict';
import { fmtInt } from '../../lib/format';
import { useCreateLoadingPlan } from '../../hooks/useFulfilment';
import {
  applyStockList,
  deleteLoadingPlan,
  getFulfilmentSuppliers,
  previewStockList,
  testStockList,
  type LoadingPlanRecord,
  type PlanDocumentKind,
  type StockListPreview,
} from '../../services/fulfilmentService';
import {
  applyProformaInvoice,
  previewProformaInvoice,
  type ProformaInvoicePreview,
  type RevisionSelection,
} from '../../services/proformaInvoiceService';
import { verdictFromPreview } from '../../proforma-invoices/components/ProformaUploadDialog';

/**
 * "Plan a container" - the ONE way onto a loading plan (R4, AC-A4/A5).
 *
 * One decision, so one dialog. It used to be two: this popup asked who and until when, then
 * handed over to a SECOND dialog for the file, which made an errand out of what is a single
 * sentence ("plan this supplier's next container, here is what they sent me"). The dropzone
 * and the existing two-step Test/Confirm (`useTwoStepUpload`, shared with every other SCM
 * upload) now run in place; the stock-list and proforma dialogs keep serving their own pages
 * unchanged, and nothing about either read is re-implemented here.
 *
 * Confirm does three things in order, and since S6 that order is: create the PLAN, apply the
 * file INTO it (`loading_plan_id`), then open it. The plan has to exist first because it is
 * what the rows are stamped with - that stamp is the whole of "a plan owns its statement",
 * and without it a plan read whatever the supplier had sent most recently, from any plan.
 * An apply that fails deletes the plan it just made, so a refused file never leaves an empty
 * record behind (AC-F2). The retained sheet is pointed at by the server during the apply,
 * so there is nothing to look up here between the two calls.
 *
 * "No file" is the third answer, and it is a real one: a supplier whose list or proforma is
 * already held needs no upload at all, and forcing one is what made the old toolbar's two
 * Upload buttons look mandatory.
 */

/** Every revision candidate, ticked - the file's own numbers decide (R24, same as the PI
 *  dialog). A wrong link is undone on the invoice's detail page, not adjudicated here. */
function revisionsFrom(preview: ProformaInvoicePreview | null): RevisionSelection {
  if (!preview) return {};
  return Object.fromEntries(
    preview.documents
      .filter((doc) => doc.revision_candidate)
      .map((doc) => [String(doc.index), doc.revision_candidate!.invoice_id]),
  );
}

export function PlanContainerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const router = useRouter();
  const [supplierId, setSupplierId] = useState('');
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(null);
  const [planHorizonDate, setPlanHorizonDate] = useState('');
  const [docKind, setDocKind] = useState<PlanDocumentKind>('stock_list');
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const create = useCreateLoadingPlan();

  // The proforma apply needs the read Test already took (it files revision candidates), and
  // Test is never mandatory, so the read is kept here and taken on the Confirm press when
  // there is none. Same shape as `ProformaUploadDialog`.
  const proformaPreviewRef = useRef<ProformaInvoicePreview | null>(null);

  /** The plan the current Confirm created, so a failing apply knows what to take back and
   *  the navigation knows where to land. */
  const startedPlanRef = useRef<LoadingPlanRecord | null>(null);

  useEffect(() => {
    if (!open) return;
    setSupplierId('');
    setSupplierOption(null);
    setPlanHorizonDate('');
    setDocKind('stock_list');
    setStarting(false);
    setStartError(null);
    proformaPreviewRef.current = null;
    startedPlanRef.current = null;
  }, [open]);

  const createPlan = () =>
    create.mutateAsync({
      supplier_id: supplierId,
      plan_horizon_date: planHorizonDate || null,
      document_kind: docKind,
      // Stamped by the server while the file is being applied (S6): the sheet is retained
      // during that same call, so there is nothing for this dialog to look up. Null on a
      // proforma or a "No file" plan, which have no retained sheet of their own.
      source_attachment_id: null,
    });

  const openPlan = (plan: LoadingPlanRecord) => {
    onOpenChange(false);
    router.push(`/scm/loading-plan/${plan.id}`);
  };

  /** The "No file" answer: there is no upload, so the plan is the whole of Confirm (R4). */
  const startPlan = async () => {
    setStarting(true);
    setStartError(null);
    try {
      openPlan(await createPlan());
    } catch (e) {
      setStartError(e instanceof Error ? e.message : 'Failed to start the plan.');
    } finally {
      setStarting(false);
    }
  };

  const upload = useTwoStepUpload<StockListPreview | ProformaInvoicePreview, unknown>({
    open,
    preview: (file) =>
      docKind === 'proforma'
        ? previewProformaInvoice(file, supplierId)
        : previewStockList(file, supplierId),
    apply: async (file) => {
      // The plan FIRST (S6): every row this apply writes carries its id, which is what
      // makes the statement the plan's own rather than the supplier's latest.
      const plan = await createPlan();
      startedPlanRef.current = plan;
      try {
        if (docKind === 'proforma') {
          const read =
            proformaPreviewRef.current ?? (await previewProformaInvoice(file, supplierId));
          return await applyProformaInvoice(
            file,
            supplierId,
            revisionsFrom(read),
            null,
            plan.id,
          );
        }
        return await applyStockList(file, supplierId, plan.id);
      } catch (e) {
        // AC-F2: the file was refused, so the plan it was for goes with it. Nobody is left
        // holding an empty record they did not ask for and cannot tell from a real one.
        startedPlanRef.current = null;
        await deleteLoadingPlan(plan.id).catch(() => undefined);
        throw e;
      }
    },
    test: docKind === 'proforma' ? undefined : (file) => testStockList(file, supplierId),
    onApplied: () => {
      const plan = startedPlanRef.current;
      if (plan) openPlan(plan);
    },
  });

  const { preview, previewing, applying, error } = upload;

  useEffect(() => {
    proformaPreviewRef.current =
      docKind === 'proforma' ? ((preview as ProformaInvoicePreview | null) ?? null) : null;
  }, [preview, docKind]);

  // The verdict card. The stock list has its own `?validate_only=true` endpoint (the hook
  // runs it alongside the preview); the proforma channel derives the same shape from the
  // read it already took, rather than costing the operator a second press.
  const proformaVerdict: UploadTestResult | null =
    docKind === 'proforma' && preview ? verdictFromPreview(preview as ProformaInvoicePreview) : null;
  const verdict = proformaVerdict ?? upload.testResult;
  const stockSummary =
    docKind === 'stock_list' && preview && 'rows' in ((preview as StockListPreview).summary ?? {})
      ? (preview as StockListPreview).summary
      : null;

  const needsFile = docKind !== 'none';
  const busy = starting || applying || previewing || upload.testing || create.isPending;
  const canStart =
    !!supplierId &&
    !busy &&
    (needsFile ? upload.canConfirm && (!proformaVerdict || proformaVerdict.valid) : true);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Plan a container</DialogTitle>
          <DialogDescription>
            {needsFile
              ? 'Test reads the file. Confirm applies it and opens the new plan.'
              : 'Start the plan from what is already on file for this supplier.'}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
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
              disabled={busy}
            />
          </div>

          <div>
            <Label htmlFor="plan-container-horizon" className="mb-1 block text-xs">
              Sales order cut-off
            </Label>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                id="plan-container-horizon"
                type="date"
                className="w-44"
                value={planHorizonDate}
                disabled={busy}
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
              <span className="text-2xs text-muted-foreground">
                Empty = every open order counts.
              </span>
            </div>
          </div>

          <div>
            <Label className="mb-1 block text-xs">Document</Label>
            <RadioGroup
              value={docKind}
              onValueChange={(next) => {
                setDocKind(next as PlanDocumentKind);
                // A verdict belongs to the channel it was read on, so switching channels
                // drops the file with it rather than confirming a stock list as a proforma.
                upload.choose(null);
              }}
              className="grid-cols-1 sm:grid-cols-3"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="stock_list" id="plan-container-doc-stock" />
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
              <div className="flex items-center gap-2">
                <RadioGroupItem value="none" id="plan-container-doc-none" />
                <Label htmlFor="plan-container-doc-none" className="text-sm font-normal">
                  No file
                </Label>
              </div>
            </RadioGroup>
          </div>

          {needsFile ? (
            <FileDropzone
              files={upload.file ? [upload.file] : []}
              onFilesChange={(next) => upload.choose(next[0] ?? null)}
              onReject={upload.reject}
              accept={upload.accept}
              maxSizeMb={MAX_SIZE_MB}
              disabled={!supplierId || busy}
              aria-label={
                docKind === 'proforma' ? 'Proforma invoice file' : 'Supplier stock list file'
              }
            />
          ) : null}

          {previewing ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the file...
            </p>
          ) : null}

          {error || startError ? (
            <Alert variant="destructive">
              <AlertDescription>{error ?? startError}</AlertDescription>
            </Alert>
          ) : null}

          {stockSummary ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <CountTile label="Items" value={stockSummary.rows} />
              <CountTile label="Packed" value={stockSummary.qty_packed} />
              <CountTile label="Unfinished" value={stockSummary.qty_unfinished} />
              <CountTile label="Replaces" value={(preview as StockListPreview).rows_held_now} />
            </div>
          ) : null}

          {stockSummary && stockSummary.items_unmatched > 0 ? (
            <p className="text-2xs text-muted-foreground">
              {fmtInt(stockSummary.items_unmatched)}{' '}
              {stockSummary.items_unmatched === 1
                ? 'model number is not in the catalogue. It is kept, but nothing can be loaded against it.'
                : 'model numbers are not in the catalogue. They are kept, but nothing can be loaded against them.'}
            </p>
          ) : null}

          {verdict ? <UploadTestVerdict result={verdict} /> : null}
        </DialogBody>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          {needsFile ? (
            <Button
              variant="outline"
              onClick={() => void upload.runTest()}
              disabled={!supplierId || !upload.file || busy}
              title={!supplierId ? 'Choose a supplier first' : undefined}
            >
              {upload.testing ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <TestTube className="size-4" />
              )}
              Test
            </Button>
          ) : null}
          <Button
            onClick={() => void (needsFile ? upload.confirm() : startPlan())}
            disabled={!canStart}
            title={!supplierId ? 'Choose a supplier first' : undefined}
            data-testid="plan-container-confirm"
          >
            {busy ? <LoaderCircle className="size-4 animate-spin" /> : null}
            {needsFile ? 'Confirm and start plan' : 'Start plan'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PlanContainerDialog;
