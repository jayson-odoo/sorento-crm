'use client';

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
import {
  CopyCapNote,
  MAX_COPY_TARGETS,
  pickedLine,
  useProductTargetPicker,
} from '../../products/[id]/components/ProductTargetPicker';
import { useAddPartyProducts, useCostingRows } from '../hooks/useCosting';

function Picker({
  customerId,
  alreadyAddedIds,
  onDone,
}: {
  customerId: string;
  alreadyAddedIds: string[];
  onDone: () => void;
}) {
  const { picked, overCap, grid } = useProductTargetPicker(undefined, { alreadyAddedIds });
  const add = useAddPartyProducts();

  const submit = async () => {
    if (!picked.length || overCap) return;
    try {
      await add.mutateAsync({ customerId, productIds: picked });
      onDone();
    } catch {
      // The hook toasted the reason; the picks stay.
    }
  };

  return (
    <>
      <DialogBody className="min-h-0 flex-1 overflow-y-auto">
        {grid}
        <div className="pt-3">
          <CopyCapNote />
        </div>
      </DialogBody>
      <DialogFooter className="flex-wrap items-center gap-2">
        <span className="mr-auto text-sm text-muted-foreground" aria-live="polite">
          {pickedLine(picked.length)}
        </span>
        <Button variant="outline" onClick={onDone} disabled={add.isPending}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} disabled={!picked.length || overCap || add.isPending}>
          {picked.length > 0 ? `Add ${picked.length.toLocaleString('en-US')}` : 'Add products'}
        </Button>
      </DialogFooter>
    </>
  );
}

/**
 * Add products to a party's costing list (AC-CG-12): the shared product picker, products already
 * on the list marked and never re-sent, up to 500 per add.
 */
export function AddCostingProductsDialog({
  open,
  onOpenChange,
  customerId,
  partyName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string;
  partyName: string;
}) {
  // The party's list as the picker should see it: one page of up to MAX rows is enough to mark
  // them; the server ignores a repeat anyway ("already").
  const { data } = useCostingRows({ party_id: customerId, page: 1, limit: MAX_COPY_TARGETS }, open);
  const alreadyAddedIds = (data?.data ?? []).map((r) => r.product_id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex max-h-[90dvh] w-[calc(100vw-2rem)] max-w-5xl flex-col"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle className="pe-8 break-words">Add products to {partyName}</DialogTitle>
          <DialogDescription className="sr-only">Pick the products to add to this party.</DialogDescription>
        </DialogHeader>
        {open ? (
          <Picker customerId={customerId} alreadyAddedIds={alreadyAddedIds} onDone={() => onOpenChange(false)} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

export default AddCostingProductsDialog;
