'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle, Network, TrendingUp, Warehouse } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useWarehouseOptions } from '../../hooks/useScmOptions';
import type { BuyScope, CreateReorderRunRequest } from '../types/reorder.types';

const SCOPES: { value: BuyScope; label: string; icon: typeof Network; help: string }[] = [
  {
    value: 'network',
    label: 'Network',
    icon: Network,
    help: 'Aggregate demand across the selected warehouses into one buy quantity, then auto-allocate it back per warehouse.',
  },
  {
    value: 'warehouse',
    label: 'Per warehouse',
    icon: Warehouse,
    help: 'Plan each selected warehouse independently — a separate buy quantity per location.',
  },
];

export function RunPlanningModal({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (req: CreateReorderRunRequest) => void;
  isSubmitting: boolean;
}) {
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [buyScope, setBuyScope] = useState<BuyScope>('network');
  const [includeMarket, setIncludeMarket] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    data: warehouseOptions,
    isLoading: warehousesLoading,
    isError: warehousesError,
  } = useWarehouseOptions();

  useEffect(() => {
    if (!open) return;
    setWarehouses([]);
    setBuyScope('network');
    setIncludeMarket(false);
    setError(null);
  }, [open]);

  const submit = () => {
    setError(null);
    if (warehouses.length === 0) {
      setError('Select at least one warehouse to plan for.');
      return;
    }
    onSubmit({
      warehouse_codes: warehouses,
      buy_scope: buyScope,
      budget_id: null,
      include_market: includeMarket,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Run planning</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-5">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div>
            <Label className="mb-1 block">Warehouses</Label>
            <SearchableMultiSelect
              value={warehouses}
              onChange={setWarehouses}
              options={warehouseOptions ?? []}
              disabled={warehousesLoading}
              placeholder={
                warehousesLoading ? 'Loading warehouses…' : 'Select warehouses to plan for'
              }
              emptyMessage={
                warehousesError ? 'Could not load warehouses.' : 'No warehouses found.'
              }
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Which warehouses to evaluate for reorder.
            </p>
          </div>

          <div>
            <Label className="mb-1.5 block">Buy scope</Label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {SCOPES.map((s) => {
                const active = buyScope === s.value;
                const Icon = s.icon;
                return (
                  <button
                    key={s.value}
                    type="button"
                    onClick={() => setBuyScope(s.value)}
                    aria-pressed={active}
                    className={cn(
                      'flex flex-col gap-1 rounded-lg border p-3 text-start transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      active
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-border hover:bg-muted/50',
                    )}
                  >
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      <Icon className="size-4 shrink-0" aria-hidden />
                      {s.label}
                    </span>
                    <span className="text-2xs leading-snug text-muted-foreground">{s.help}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <Label className="mb-1.5 block">Market signals</Label>
            <button
              type="button"
              onClick={() => setIncludeMarket((v) => !v)}
              aria-pressed={includeMarket}
              className={cn(
                'flex w-full items-start gap-2.5 rounded-lg border p-3 text-start transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                includeMarket
                  ? 'border-primary bg-primary/5 ring-1 ring-primary'
                  : 'border-border hover:bg-muted/50',
              )}
            >
              <Checkbox checked={includeMarket} className="mt-0.5" tabIndex={-1} aria-hidden />
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  <TrendingUp className="size-4 shrink-0" aria-hidden />
                  Factor in market signals
                </span>
                <span className="mt-0.5 block text-2xs leading-snug text-muted-foreground">
                  Trending categories fund first when the budget is tight. Affects funding
                  priority only — order quantities are unchanged.
                </span>
              </span>
            </button>
          </div>

          <div>
            <Label className="mb-1 block text-muted-foreground">Budget</Label>
            <div
              className="flex h-9 items-center justify-between rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground"
              title="Budget-constrained ranking is not yet available"
            >
              <span>No budget cap</span>
              <span className="rounded-sm bg-muted px-1.5 py-0.5 text-2xs font-medium">
                Not yet available
              </span>
            </div>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={isSubmitting}>
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Run planning
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
