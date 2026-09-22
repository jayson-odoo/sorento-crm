'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { searchProductOptions } from '../../services/scmOptionsService';
import { useWarehouseOptions } from '../../hooks/useScmOptions';
import { getCandidateOrders } from '../services/reorderRunService';

/** Start Plan inputs (M8-D5, revised; captain 20 Aug dropped the cash budget field -
 *  budget stays a backend/post-run capability only, tightened afterwards on the plan
 *  via `CashBudgetPanel`/`applyBudget`, never set at launch). No market-insight
 *  toggle - market never enters a run; it reaches the plan only through the chat
 *  (Slice E). The legacy `buy_scope` is removed. Warehouse is MULTI-select and
 *  OPTIONAL (pick several, or leave it empty for every warehouse) so a plan can cover
 *  any subset - or the same ground as the daily run. */
export interface ManualPlanInputs {
  /**
   * Optional warehouse scope. **Empty means every warehouse** (P1, captain 25 Aug),
   * exactly as empty products already means every product - the backend resolves an
   * empty list to every active warehouse, so an unnarrowed manual plan covers the
   * same ground as the scheduled daily run.
   */
  warehouse_codes: string[];
  /**
   * Optional product scope (AC-B8a). **Empty means all products**, so the existing
   * behaviour and the scheduled daily run are unchanged. Human product codes, never
   * ids. This is an explicit product list and NOT a reinstatement of the removed
   * `buy_scope` category filter.
   */
  product_codes: string[];
  /**
   * S4 (`reorder-feedback-9sep.md`, 9 Sep 2026): the window's START. Empty means no
   * lower bound - a line dated before it still counts, the same reading an undated line
   * already gets. `YYYY-MM-DD` when set.
   */
  plan_horizon_start: string;
  /**
   * "Sales orders needed", To (captain, 20 Aug; renamed in the revamp, S4 gave it a
   * From beside it). **Empty means no horizon** - every open SO line is planned
   * regardless of when it is needed, today's behaviour. `YYYY-MM-DD` when set; demand
   * needed after it is excluded from this run's netting, and demand carrying no date is
   * always still counted.
   */
  plan_horizon_date: string;
  /**
   * Which leg of demand to net (`reorder-plan-demand-class-orders`, 21 Sep). Absent
   * means Demand = All - both legs, today's behaviour. Present only when the buyer
   * picked Project or Dealer.
   */
  demand_class?: 'project' | 'retail';
  /**
   * The SO scope, present only when `demand_class === 'project'` - the buyer's final
   * selection from the Orders picker, `[]` when everything was unticked (still means
   * "every project order in range", not "none").
   */
  so_numbers?: string[];
}

/** Demand = Project / Dealer / All (R4). "Dealer" is retail - the vocabulary a buyer
 *  reads is not the closed `demand_class` one on the wire. */
const DEMAND_OPTIONS = [
  { value: 'project', label: 'Project' },
  { value: 'retail', label: 'Dealer' },
];

/** Today, as the `YYYY-MM-DD` a `<input type="date">` needs - local calendar date, not
 *  `toISOString()`'s UTC one, which reads as yesterday or tomorrow depending on the
 *  browser's own offset. */
function todayDateInputValue(): string {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Start Plan - the one way a person launches a run (plan 4.2). The scheduled daily run
 * (all warehouses, full budget) fires without this modal.
 *
 * Fields in the order the buyer decides them: how far ahead to plan, then which warehouses,
 * then which products. Every one is optional and empty means "everything", which is what
 * makes Start Plan a single click on the day the answer is "the usual".
 *
 * There is no Select all: empty ALREADY means every warehouse, so a button that filled the
 * box with every code produced the same run by a longer route and read as though leaving it
 * blank would do something else.
 */
export function RunPlanningModal({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (inputs: ManualPlanInputs) => void;
  isSubmitting: boolean;
}) {
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [products, setProducts] = useState<string[]>([]);
  const [horizonStart, setHorizonStart] = useState('');
  const [horizon, setHorizon] = useState('');
  /** "Inquiries raised" From/To (`reorder-plan-raised-filter`, 22 Sep 2026) - narrows the
   *  Orders pre-selection to the rows raised in this window (R1: a row's first upload
   *  day, since the book carries no raise date of its own). Shown only while
   *  Demand = Project. */
  const [raisedFrom, setRaisedFrom] = useState('');
  const [raisedTo, setRaisedTo] = useState('');
  const [error, setError] = useState<string | null>(null);
  /** Labels of every product this modal has seen come back from the server, so a chip for a
   *  code that is not on the page currently loaded still reads as its name. */
  const [productLabels, setProductLabels] = useState<Record<string, string>>({});
  /** '' reads as Demand = All (R4) - the same "empty means everything" reading every other
   *  field in this modal already uses. */
  const [demand, setDemand] = useState<'' | 'project' | 'retail'>('');
  const [soNumbers, setSoNumbers] = useState<string[]>([]);
  /** Once the buyer has edited the Orders pick by hand, the range no longer overwrites it
   *  (V4) - re-derived from the query result until then, kept afterwards. */
  const touchedOrdersRef = useRef(false);

  const {
    data: warehouseOptions,
    isLoading: warehousesLoading,
    isError: warehousesError,
  } = useWarehouseOptions();

  /** Products are SEARCHED ON THE SERVER, never a static list: `products/select` answers with
   *  its own default of 100 rows against ~22,000 active products, so the list this field used
   *  to hold covered 0.5% of the catalogue and said "no products found" for the rest (R19
   *  browser run: CB2907 and SRTWT7445-LV were unpickable). Same helper the sales-order and
   *  purchase-order line pickers use. */
  const fetchProductOptions = useCallback(async (query: string) => {
    const options = await searchProductOptions(query);
    setProductLabels((prev) => {
      const next = { ...prev };
      for (const opt of options) next[opt.value] = opt.label;
      return next;
    });
    return options;
  }, []);

  const selectedProductOptions = useMemo(
    () => products.map((code) => ({ value: code, label: productLabels[code] ?? code })),
    [products, productLabels],
  );

  useEffect(() => {
    if (!open) return;
    setWarehouses([]);
    setProducts([]);
    setHorizonStart('');
    setHorizon('');
    setRaisedFrom('');
    setRaisedTo('');
    setError(null);
    setProductLabels({});
    setDemand('');
    setSoNumbers([]);
    touchedOrdersRef.current = false;
  }, [open]);

  /** Every open project SO with an OI row, for the Orders picker - fetched while
   *  Demand = Project OR All (Lane D, AC-D1: "the same candidate query" for both; Dealer
   *  has no picker), and re-fetched as either range changes (the delivery range narrows
   *  `rows_in_range`, the raise window narrows `rows_raised_in_window`; either drives the
   *  pre-selection below). */
  const {
    data: candidateOrders,
    isLoading: candidatesLoading,
    isError: candidatesError,
  } = useQuery({
    queryKey: ['reorder', 'candidate-orders', horizonStart, horizon, raisedFrom, raisedTo],
    queryFn: () =>
      getCandidateOrders({
        from: horizonStart || undefined,
        to: horizon || undefined,
        raised_from: raisedFrom || undefined,
        raised_to: raisedTo || undefined,
      }),
    enabled: open && demand !== 'retail',
  });

  // Pre-select every SO with a line in range AND a row raised in the window (J1 + R2),
  // re-derived on every fresh result UNTIL the buyer has touched the list by hand (V4) -
  // a range or raise-window edit before that point still updates the pick; one after
  // keeps whatever they chose. With no raise window `rows_raised_in_window` equals
  // `rows_total`, so this is unchanged from before the raise window existed. Runs for
  // All too (Lane D) - Dealer never reaches here (the fetch above is disabled for it).
  useEffect(() => {
    if (demand === 'retail' || touchedOrdersRef.current || !candidateOrders) return;
    setSoNumbers(
      candidateOrders
        .filter((o) => o.rows_in_range > 0 && o.rows_raised_in_window > 0)
        .map((o) => o.so_number),
    );
  }, [candidateOrders, demand]);

  const handleSoNumbersChange = (next: string[]) => {
    touchedOrdersRef.current = true;
    setSoNumbers(next);
  };

  /** `so_number - project label or customer name`, trimmed when neither is on file - the
   *  option's accessible name (also the closed-trigger label's source when no summary
   *  suffix applies). The two-line description (former "N lines in range[, raised N]")
   *  is gone - the owner's Lane D fix-round-1 ruling retired it everywhere in favour of
   *  the one-line menu row below. */
  const orderOptions = useMemo(
    () =>
      (candidateOrders ?? []).map((o) => {
        const suffix = o.project_label ?? o.customer_name ?? '';
        return {
          value: o.so_number,
          label: suffix ? `${o.so_number} - ${suffix}` : o.so_number,
        };
      }),
    [candidateOrders],
  );

  /** Awaiting-ack counts, kept apart from `orderOptions` so `renderOption` can colour just
   *  that part of the row (27 Aug ruling: never bought against, so it has to stay visible
   *  before Start). */
  const awaitingBySoNumber = useMemo(() => {
    const map = new Map<string, number>();
    for (const o of candidateOrders ?? []) map.set(o.so_number, o.rows_awaiting);
    return map;
  }, [candidateOrders]);

  /** SO number -> customer name, for the one-line menu row (owner ruling, Lane D fix
   *  round 1: "<SO number> - <customer>", the awaiting count appended only when
   *  non-zero - under Demand = Project AND All alike, full stop). */
  const customerBySoNumber = useMemo(() => {
    const map = new Map<string, string>();
    for (const o of candidateOrders ?? []) map.set(o.so_number, o.customer_name ?? '');
    return map;
  }, [candidateOrders]);

  /** The Orders field's own closed-trigger label (AC-D1: ONE line, the first two SO
   *  numbers then `+x` for the rest - `SO418869, SO419517 +12`, no chip wall) - shared by
   *  Demand = All and Demand = Project alike ("Same trigger under Demand = Project"). */
  const renderOrdersTriggerLabel = useCallback(
    (selected: { value: string; label: string }[]) => {
      if (selected.length === 0) return 'Every project order in range';
      const shown = selected.slice(0, 2).map((o) => o.value).join(', ');
      const rest = selected.length - 2;
      return rest > 0 ? `${shown} +${rest}` : shown;
    },
    [],
  );

  const today = todayDateInputValue();

  const submit = () => {
    setError(null);
    // S4: To before From nets nothing either - the same class of silent-empty-run
    // mistake the past-cutoff guard below catches, and checked first: a To date that
    // is both in the past AND before From is this mistake, not that one.
    if (horizonStart && horizon && horizon < horizonStart) {
      setError('The To date cannot be before the From date.');
      return;
    }
    // A past cutoff nets every open line against demand that "must" have been needed
    // before today, which is every line - the run then silently returns zero demand
    // rather than saying why (nit, code review 20 Aug 2026).
    if (horizon && horizon < today) {
      setError('The cut-off cannot be in the past - it would leave the run with no demand.');
      return;
    }
    onSubmit({
      // Empty = every warehouse (P1), the same rule products already carry: narrowing
      // is the exception, and requiring a pick made every manual run harder than the
      // daily one it stands in for.
      warehouse_codes: warehouses,
      // Empty = all products. Products are deliberately NOT required: narrowing to
      // one is the exception, and forcing a pick would make every run harder than
      // the daily one it stands in for.
      product_codes: products,
      // Empty = no lower bound: a line dated before it still counts (G2 ruling).
      plan_horizon_start: horizonStart,
      // Empty = no horizon (today's behaviour): every open SO line is planned
      // regardless of when it is needed.
      plan_horizon_date: horizon,
      // Demand = All sends no demand_class (V3): the modal predates demand scoping and
      // an unnarrowed run must stay indistinguishable from before this existed.
      ...(demand ? { demand_class: demand } : {}),
      // The buyer's FINAL selection - `[]` when everything was unticked, which still
      // means "every project order in range" (design 4.6), not "none" - always sent
      // under Project, never omitted. Under All (Lane D, AC-D2/D3) `so_numbers` MAY
      // accompany the run to narrow its own project legs, sent only when there is
      // something to narrow by - an All run with nothing picked (no candidates, or the
      // picker never loaded) stays indistinguishable from before this lane, matching
      // every pre-Lane-D test's exact payload.
      ...(demand === 'project' || (demand === '' && soNumbers.length > 0)
        ? { so_numbers: soNumbers }
        : {}),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Start Plan</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-5">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div>
            <Label htmlFor="plan-demand" className="mb-1 block">Demand</Label>
            <SearchableSelect
              id="plan-demand"
              value={demand}
              onChange={(v) => setDemand(v as '' | 'project' | 'retail')}
              options={DEMAND_OPTIONS}
              clearable
              placeholder="All"
            />
          </div>

          <div>
            {/* Renamed by Lane D (AC-D1b, owner ruling: "this order range only is for
                project") - the range now narrows only the two project legs on an All
                run; the retail SO-book leg plans every open line regardless of it, same
                as an unhorizoned run today. */}
            <Label className="mb-1 block">Project delivery range</Label>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label htmlFor="plan-window-start" className="mb-1 block text-2xs text-muted-foreground">
                  From
                </Label>
                <Input
                  id="plan-window-start"
                  type="date"
                  value={horizonStart}
                  onChange={(e) => setHorizonStart(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="plan-cutoff" className="mb-1 block text-2xs text-muted-foreground">
                  To
                </Label>
                <Input
                  id="plan-cutoff"
                  type="date"
                  min={today}
                  value={horizon}
                  onChange={(e) => setHorizon(e.target.value)}
                />
              </div>
            </div>
            <p className="mt-1 text-2xs text-muted-foreground">
              Empty = every open order counts.
            </p>
          </div>

          {demand === 'project' ? (
            <div>
              <Label className="mb-1 block">Inquiries raised</Label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label htmlFor="plan-raised-from" className="mb-1 block text-2xs text-muted-foreground">
                    Raised from
                  </Label>
                  <Input
                    id="plan-raised-from"
                    type="date"
                    value={raisedFrom}
                    onChange={(e) => setRaisedFrom(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="plan-raised-to" className="mb-1 block text-2xs text-muted-foreground">
                    Raised to
                  </Label>
                  <Input
                    id="plan-raised-to"
                    type="date"
                    value={raisedTo}
                    onChange={(e) => setRaisedTo(e.target.value)}
                  />
                </div>
              </div>
              <p className="mt-1 text-2xs text-muted-foreground">
                Empty = any raise date. Pre-selects the matching orders; the list still
                shows them all.
              </p>
            </div>
          ) : null}

          {/* Lane D (AC-D1): the Orders picker now shows for All as well as Project -
              same candidate query, same "everything in range ticked by default" rule,
              same trigger. Dealer has no picker (nothing to narrow against a retail
              run). */}
          {demand !== 'retail' ? (
            <div>
              <Label className="mb-1 block">Orders</Label>
              <SearchableMultiSelect
                value={soNumbers}
                onChange={handleSoNumbersChange}
                options={orderOptions}
                disabled={candidatesLoading}
                placeholder={candidatesLoading ? 'Loading orders...' : 'Every project order in range'}
                emptyMessage={
                  candidatesError ? 'Could not load orders.' : 'No project orders found.'
                }
                renderTriggerLabel={renderOrdersTriggerLabel}
                // Owner ruling (Lane D fix round 1): one-line menu rows under Project
                // AND All, full stop - "<SO number> - <customer>", the awaiting-ack
                // count appended only when it is non-zero. The old two-line row
                // (description + "N lines in range") is gone everywhere, not just All.
                renderOption={(opt) => {
                  const awaiting = awaitingBySoNumber.get(opt.value) ?? 0;
                  const customer = customerBySoNumber.get(opt.value) ?? '';
                  const base = customer ? `${opt.value} - ${customer}` : opt.value;
                  return (
                    <span className="break-words">
                      {base}
                      {awaiting > 0 ? (
                        <span className="text-warning">{`, ${awaiting} awaiting ack`}</span>
                      ) : null}
                    </span>
                  );
                }}
              />
              <p className="mt-1 text-2xs text-muted-foreground">
                Empty = every project order in range.
              </p>
            </div>
          ) : null}

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label>Warehouses</Label>
              {warehouses.length ? (
                <button
                  type="button"
                  className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                  onClick={() => setWarehouses([])}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            <SearchableMultiSelect
              value={warehouses}
              onChange={setWarehouses}
              options={warehouseOptions ?? []}
              disabled={warehousesLoading}
              placeholder={warehousesLoading ? 'Loading warehouses...' : 'All warehouses'}
              emptyMessage={warehousesError ? 'Could not load warehouses.' : 'No warehouses found.'}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Leave empty to plan every warehouse.
            </p>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label>Products</Label>
              {products.length ? (
                <button
                  type="button"
                  className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                  onClick={() => setProducts([])}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            <SearchableMultiSelect
              value={products}
              onChange={setProducts}
              fetchOptions={fetchProductOptions}
              selectedOptions={selectedProductOptions}
              placeholder="All products"
              emptyMessage="No products found."
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Leave empty to plan every product.
            </p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={isSubmitting}>
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Start Plan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
