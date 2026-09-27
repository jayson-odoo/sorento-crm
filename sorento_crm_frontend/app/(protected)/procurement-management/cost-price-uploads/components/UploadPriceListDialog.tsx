'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DatePicker } from '@/components/ui/date-picker';
import { FileDropzone } from '@/components/common/FileDropzone';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { toast } from '@/lib/toast';
import { searchSuppliersForSelect } from '../../suppliers/services/supplierService';
import { OpenSetExistsError, useProbeCostPriceFile, useUploadCostPriceFile } from '../hooks/useCostPriceChangeSets';
import { formatPlainDate } from '../lib/formatPlainDate';

const CURRENCY_OPTIONS: SearchableSelectOption[] = [
  { value: 'CNY', label: 'CNY, Chinese yuan' },
  { value: 'USD', label: 'USD, US dollar' },
  { value: 'MYR', label: 'MYR, Malaysian ringgit' },
  { value: 'EUR', label: 'EUR, Euro' },
];

function toDateOnly(date: Date | undefined): string | null {
  if (!date) return null;
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function UploadPriceListDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const router = useRouter();
  const [files, setFiles] = React.useState<File[]>([]);
  const [supplierId, setSupplierId] = React.useState('');
  const [supplierOption, setSupplierOption] = React.useState<SearchableSelectOption | null>(null);
  const [currency, setCurrency] = React.useState('');
  const [startDate, setStartDate] = React.useState<Date | undefined>();
  const [endDate, setEndDate] = React.useState<Date | undefined>();
  const [openSet, setOpenSet] = React.useState<{ id: string; code: string } | null>(null);

  const probe = useProbeCostPriceFile();
  const upload = useUploadCostPriceFile();

  React.useEffect(() => {
    if (open) {
      setFiles([]);
      setSupplierId('');
      setSupplierOption(null);
      setCurrency('');
      setStartDate(undefined);
      setEndDate(undefined);
      setOpenSet(null);
    }
  }, [open]);

  const probeResult = probe.data;

  React.useEffect(() => {
    if (!probeResult) return;
    if (probeResult.suggested_supplier) {
      setSupplierId(probeResult.suggested_supplier.id);
      setSupplierOption({
        value: probeResult.suggested_supplier.id,
        label: probeResult.suggested_supplier.supplier_name,
        searchText: `${probeResult.suggested_supplier.supplier_code} ${probeResult.suggested_supplier.supplier_name}`,
      });
    }
    if (probeResult.currency.code) setCurrency(probeResult.currency.code);
  }, [probeResult]);

  const onFilesChange = (next: File[]) => {
    setFiles(next);
    setOpenSet(null);
    const file = next[0];
    if (file) probe.mutate(file);
  };

  const endBeforeStart = Boolean(startDate && endDate && endDate < startDate);
  const canSubmit = files.length > 0 && Boolean(supplierId) && Boolean(currency) && !endBeforeStart && !upload.isPending;

  const onSubmit = async () => {
    if (!canSubmit || !files[0]) return;
    try {
      const detail = await upload.mutateAsync({
        file: files[0],
        supplier: supplierOption
          ? {
              id: supplierId,
              supplier_code: supplierOption.searchText?.split(' ')[0] ?? supplierOption.label,
              supplier_name: supplierOption.label,
            }
          : { id: supplierId, supplier_code: supplierId, supplier_name: supplierId },
        currency,
        start_date: toDateOnly(startDate),
        end_date: toDateOnly(endDate),
      });
      onOpenChange(false);
      router.push(`/procurement-management/cost-price-uploads/${detail.id}`);
    } catch (error) {
      if (error instanceof OpenSetExistsError) {
        setOpenSet(error.open_set);
      } else {
        toast.error(error instanceof Error ? error.message : 'Failed to upload the price list');
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload price list</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <FileDropzone
            accept=".xlsx,.xls"
            maxSizeMb={25}
            files={files}
            onFilesChange={onFilesChange}
            onReject={(file, reason) =>
              toast.error(reason === 'size' ? `${file.name} is larger than 25 MB` : `${file.name} is not an Excel file`)
            }
            aria-label="Supplier price list file"
          />

          {openSet ? (
            <Alert variant="warning">
              <AlertDescription className="flex flex-wrap items-center gap-2">
                <span>{openSet.code} is already open for this supplier.</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => router.push(`/procurement-management/cost-price-uploads/${openSet.id}`)}
                >
                  Open {openSet.code}
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          {probe.isPending ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" /> Reading the file...
            </p>
          ) : null}

          {probeResult ? (
            <p className="text-sm text-muted-foreground">
              {probeResult.sheets.length} sheets, {probeResult.total_rows} rows read
            </p>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="cost-price-supplier">Supplier</Label>
            <SearchableSelect
              id="cost-price-supplier"
              value={supplierId}
              onChange={setSupplierId}
              onOptionChange={setSupplierOption}
              selectedOption={supplierOption ?? undefined}
              fetchOptions={searchSuppliersForSelect}
              placeholder="Search suppliers"
              triggerClassName="w-full"
            />
            {probeResult?.suggested_supplier ? (
              <p className="text-xs text-muted-foreground">Found in the file&apos;s letterhead</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cost-price-currency">Currency</Label>
            <SearchableSelect
              id="cost-price-currency"
              value={currency}
              onChange={setCurrency}
              options={CURRENCY_OPTIONS}
              clearable
              placeholder="Select a currency"
              triggerClassName="w-full"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>
                Valid from <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <DatePicker value={startDate} onChange={setStartDate} ariaLabel="Valid from" />
            </div>
            <div className="space-y-1.5">
              <Label>
                Valid to <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <DatePicker value={endDate} onChange={setEndDate} ariaLabel="Valid to" />
              {endBeforeStart ? <p className="text-xs text-destructive">Valid to cannot be before Valid from.</p> : null}
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {probeResult?.file_date ? `File date: ${formatPlainDate(probeResult.file_date)}. ` : ''}
            Leave both dates empty for a price that always applies.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={!canSubmit}>
            {upload.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default UploadPriceListDialog;
