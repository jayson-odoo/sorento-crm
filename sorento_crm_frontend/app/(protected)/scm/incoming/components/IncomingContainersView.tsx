'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { fmtInt } from '../../lib/format';
import { useFulfilmentSuppliers } from '../../hooks/useFulfilment';
import { getIncomingShipments, type IncomingShipment } from '../../services/fulfilmentService';
import { PackingListUploadDialog } from './PackingListUploadDialog';
import { ConsolidatedPackingListPanel } from './ConsolidatedPackingListPanel';
import { AllocationPanel } from './AllocationPanel';

/**
 * Ms Tee's steps four and five: read the packing list, then decide what each container draws
 * down. Two panels rather than two pages, because the second is only ever reached from the
 * first and a page transition between them would lose which container she was looking at.
 */

export function IncomingContainersView() {
  const suppliers = useFulfilmentSuppliers();
  const [supplierId, setSupplierId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const qc = useQueryClient();

  // Read from the server rather than from what the last upload returned. A container is read
  // once and decided later, often not in the same sitting, and a refresh used to empty the
  // screen as though the import had not happened.
  const shipments = useQuery({
    queryKey: ['scm', 'fulfilment', 'incoming', supplierId],
    queryFn: () => getIncomingShipments(supplierId),
    refetchOnWindowFocus: false,
  });
  const imported = shipments.data ?? [];

  // Landing here from a "Convert to draft shipment" / "Create SPO" hand-off carries the
  // human-readable shipment NUMBER (never an id) as `?shipment=`, so the caller lands on
  // it pre-selected rather than having to find it in the list again. Consumed once, the
  // first time it matches a row - a later manual click must be free to change the
  // selection without the param fighting it on the next render. Depends on `shipments.data`
  // itself, not the `imported` fallback array - the latter is a fresh `[]` reference every
  // render while data is still loading, which would otherwise re-run this effect forever.
  const searchParams = useSearchParams();
  const deepLinkedShipment = searchParams.get('shipment');
  const consumedDeepLink = useRef(false);
  useEffect(() => {
    if (!deepLinkedShipment || consumedDeepLink.current) return;
    const match = shipments.data?.find((s) => s.shipment_number === deepLinkedShipment);
    if (match) {
      setSelected(match.shipment_id);
      consumedDeepLink.current = true;
    }
  }, [deepLinkedShipment, shipments.data]);

  // Whose lines the upload will become. The file itself never says, so the supplier chosen
  // here is the only answer, and an upload without one is refused by the server.
  const supplierName =
    (suppliers.data ?? []).find((o) => o.value === supplierId)?.label ?? null;

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <label className="text-xs text-muted-foreground" htmlFor="incoming-supplier">
              Supplier
            </label>
            <SearchableSelect
              id="incoming-supplier"
              className="mt-1 w-72"
              value={supplierId ?? ''}
              onChange={(v: string) => setSupplierId(v || null)}
              options={suppliers.data ?? []}
              placeholder="Choose a supplier"
              clearable
            />
          </div>
          <Button
            onClick={() => setUploadOpen(true)}
            disabled={!supplierId}
            title={!supplierId ? 'Choose a supplier first' : undefined}
          >
            <Upload className="size-4" />
            Upload packing list
          </Button>
        </div>
      </Card>

      {!imported.length ? (
        <Card className="p-8 text-center">
          <Boxes className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-2 text-sm font-medium">No container read yet.</p>
          <p className="text-2xs text-muted-foreground">
            Upload the pre-load list or packing list. Every container block in it becomes its own
            shipment.
          </p>
        </Card>
      ) : (
        <Card className="divide-y divide-border">
          <CardHeader className="py-3">
            <h3 className="text-sm font-semibold">
              Containers read
              <span className="ms-2 text-2xs font-normal text-muted-foreground">
                {imported.length}
              </span>
            </h3>
          </CardHeader>
          {imported.map((s) => (
            <button
              key={s.shipment_id}
              type="button"
              onClick={() => setSelected(s.shipment_id)}
              className={`flex w-full items-center justify-between gap-3 p-3 text-start hover:bg-muted/50 ${
                selected === s.shipment_id ? 'bg-muted/60' : ''
              }`}
            >
              <div className="min-w-0">
                <div className="truncate text-xs font-medium">
                  {/* A read that named neither still has to be clickable and tellable
                      apart from the next one - a blank row reads as a broken screen. */}
                  {s.container_no || s.shipment_number || 'Unnumbered container'}
                </div>
                <div className="truncate text-2xs text-muted-foreground">{subLine(s)}</div>
              </div>
              <span className="shrink-0 text-2xs text-muted-foreground">
                {fmtInt(s.lines)} lines
              </span>
            </button>
          ))}
        </Card>
      )}

      <ConsolidatedPackingListPanel shipmentId={selected} />

      {selected ? <AllocationPanel shipmentId={selected} /> : null}

      <PackingListUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        supplierId={supplierId}
        supplierName={supplierName}
        onImported={(results) => {
          qc.invalidateQueries({ queryKey: ['scm', 'fulfilment', 'incoming', supplierId] });
          setSelected(results[0]?.shipment_id ?? null);
        }}
      />
    </div>
  );
}

/**
 * The line under the container number: whose lines these are, and which shipment they sit on.
 *
 * One container is routinely loaded by two or three factories, and the header names none of
 * them once it is mixed - but the factories must not cost the shipment number its place, since
 * that is what the SPO and the GRN are keyed on. Both are shown; the shipment number is only
 * repeated when the heading above is the container number and the two differ.
 */
function subLine(s: IncomingShipment): string {
  const names = (s.suppliers ?? [])
    .map((x) => x.supplier_name ?? x.supplier_code)
    .filter(Boolean)
    .join(', ');
  const number =
    s.container_no && s.shipment_number && s.shipment_number !== s.container_no
      ? s.shipment_number
      : null;
  // Never an empty line: with no factory known, whichever number is missing is what the
  // row has left to say, and saying nothing looks like the row failed to load.
  if (!names) {
    if (!s.container_no) return 'No container number yet';
    return s.shipment_number ?? 'No shipment number';
  }
  return number ? `${number} · ${names}` : names;
}

export default IncomingContainersView;
