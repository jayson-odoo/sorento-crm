'use client';

import { Fragment, useState, type FormEvent } from 'react';
import { Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { toast } from '@/lib/toast';
import {
  COSTING_RATES_KEY,
  COSTING_ROWS_KEY,
  useCategoryRules,
  useCostingSettings,
  useCreateExchangeRate,
  useExchangeRates,
  useSaveCategoryRule,
  useSaveCostingSettings,
} from '../hooks/useCosting';
import { shortDate, trimmed } from '../lib/format';
import type {
  CategoryRule,
  CostingSettings,
  ExchangeRate,
  ExchangeRateBody,
} from '../types/costing.types';

const STATUS: Record<ExchangeRate['status'], { label: string; variant: 'success' | 'info' | 'secondary' }> = {
  scheduled: { label: 'Scheduled', variant: 'info' },
  in_force: { label: 'In force', variant: 'success' },
  past: { label: 'Past', variant: 'secondary' },
};

const METHOD_OPTIONS = [
  { value: 'primary', label: 'Primary supplier' },
  { value: 'average', label: 'Average of supplier prices' },
  { value: 'last_po', label: 'Last PO price' },
];

const MODE_OPTIONS = [
  { value: 'add', label: 'Add' },
  { value: 'multiply', label: 'Multiply' },
];

const TH = 'whitespace-nowrap px-3 py-2 text-start font-medium';

/** A positive figure typed into a box, or null for blank, zero, negative or text. */
function positive(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

// ------------------------------------------------------------------ Exchange rates

function RateForm() {
  const create = useCreateExchangeRate();
  const [currency, setCurrency] = useState('');
  const [from, setFrom] = useState('');
  const [basis, setBasis] = useState<'units' | 'myr'>('units');
  const [rate, setRate] = useState('');
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const code = currency.trim().toUpperCase();
    const value = positive(rate);
    if (!code || !from) {
      setProblem('Enter a currency and the date it starts.');
      return;
    }
    if (value === null) {
      setProblem('Enter a rate above zero.');
      return;
    }
    setProblem(null);
    const body: ExchangeRateBody = {
      currency: code,
      effective_from: from,
      ...(basis === 'units' ? { units_per_base: value } : { rate_to_base: value }),
      ...(note.trim() ? { note: note.trim() } : {}),
    };
    try {
      await create.mutateAsync(body);
      setRate('');
      setNote('');
    } catch {
      // The hook toasted the reason (a duplicate currency and date is a 409).
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3 rounded-lg border p-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor="costing-rate-currency" className="text-xs text-muted-foreground">
            Currency
          </Label>
          <Input
            id="costing-rate-currency"
            value={currency}
            maxLength={3}
            onChange={(e) => setCurrency(e.target.value)}
            className="uppercase"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="costing-rate-from" className="text-xs text-muted-foreground">
            Effective from
          </Label>
          <Input id="costing-rate-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="costing-rate-value" className="text-xs text-muted-foreground">
            Rate
          </Label>
          <NumberInput
            id="costing-rate-value"
            step="any"
            min={0}
            value={rate}
            onChange={(e) => setRate(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="costing-rate-note" className="text-xs text-muted-foreground">
            Note
          </Label>
          <Input id="costing-rate-note" value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="costing-rate-basis"
            aria-label="Units per MYR 1"
            className="size-4 accent-primary"
            checked={basis === 'units'}
            onChange={() => setBasis('units')}
          />
          Units per MYR 1
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="costing-rate-basis"
            aria-label="MYR per unit"
            className="size-4 accent-primary"
            checked={basis === 'myr'}
            onChange={() => setBasis('myr')}
          />
          MYR per unit
        </label>
        <Button type="submit" size="sm" className="ms-auto" disabled={create.isPending}>
          Add rate
        </Button>
      </div>
      {problem ? (
        <p role="alert" className="text-sm text-destructive">
          {problem}
        </p>
      ) : null}
    </form>
  );
}

function RatesTab() {
  const canWrite = useHasPermission('scm.config.manage');
  const { data, isLoading, isError, error } = useExchangeRates();
  const deletion = useDeferredRowAction({
    actionKey: 'exchange_rate.delete',
    entityType: 'exchange_rate',
    surface: 'inline',
    countdownClassName: 'w-full min-w-0',
    successMessage: 'Rate deleted.',
    invalidateKeys: [[...COSTING_RATES_KEY], [...COSTING_ROWS_KEY]],
  });
  const rows = data?.data ?? [];
  const columns = canWrite ? 7 : 6;

  return (
    <div className="space-y-4">
      {canWrite ? <RateForm /> : null}
      {isError ? (
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load the exchange rates.'}
        </p>
      ) : null}
      {isLoading ? null : rows.length ? (
        <div className="overflow-x-auto rounded-lg border">
          <table aria-label="Exchange rates" className="w-full text-sm">
            <thead className="bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className={TH}>Currency</th>
                <th className={TH}>Effective from</th>
                <th className={`${TH} text-end`}>Units per MYR 1</th>
                <th className={`${TH} text-end`}>MYR per unit</th>
                <th className={TH}>Status</th>
                <th className={TH}>Note</th>
                {canWrite ? (
                  <th className="w-px px-2 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) =>
                deletion.targetId === r.id && deletion.countdown ? (
                  <Fragment key={r.id}>
                    <tr className="text-muted-foreground">
                      <td className="px-3 py-2">{r.currency}</td>
                      <td className="whitespace-nowrap px-3 py-2">{shortDate(r.effective_from)}</td>
                      <td colSpan={columns - 2}>
                        <span className="sr-only">Deleting</span>
                      </td>
                    </tr>
                    <tr className="!border-t-0">
                      <td colSpan={columns} className="px-2 pb-2">
                        {deletion.countdown}
                      </td>
                    </tr>
                  </Fragment>
                ) : (
                  <tr key={r.id}>
                    <td className="px-3 py-2 font-medium">{r.currency}</td>
                    <td className="whitespace-nowrap px-3 py-2">{shortDate(r.effective_from)}</td>
                    <td className="px-3 py-2 text-end tabular-nums">{trimmed(r.units_per_base, 4)}</td>
                    <td className="px-3 py-2 text-end tabular-nums">{trimmed(r.rate_to_base, 6)}</td>
                    <td className="px-3 py-2">
                      <Badge variant={STATUS[r.status].variant} appearance="light" size="sm">
                        {STATUS[r.status].label}
                      </Badge>
                    </td>
                    <td className="max-w-[14rem] px-3 py-2">
                      {r.note ? (
                        <span className="block truncate" title={r.note}>
                          {r.note}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    {canWrite ? (
                      <td className="px-2 py-1">
                        <Button
                          variant="ghost"
                          mode="icon"
                          size="sm"
                          aria-label={`Delete ${r.currency} rate from ${shortDate(r.effective_from)}`}
                          onClick={() =>
                            deletion.run({
                              id: r.id,
                              subject: `the ${r.currency} rate from ${shortDate(r.effective_from)}`,
                            })
                          }
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </td>
                    ) : null}
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed py-6 text-center">
          <p className="text-sm font-medium">No exchange rates yet</p>
          <p className="text-xs text-muted-foreground">Add the first rate above.</p>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ SST and method

function SstForm({ settings }: { settings: CostingSettings }) {
  const canManage = useHasPermission('products.party_costing.manage');
  const save = useSaveCostingSettings();
  const [sst, setSst] = useState(String(settings.sst_factor));
  const [method, setMethod] = useState<string>(settings.default_method);
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = positive(sst);
    if (value === null) {
      setProblem('The SST factor must be above zero.');
      return;
    }
    if (!method) return;
    setProblem(null);
    try {
      await save.mutateAsync({ sst_factor: value, default_method: method as CostingSettings['default_method'] });
    } catch {
      // The hook toasted the reason.
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="max-w-sm space-y-4">
      <div className="flex flex-col gap-1">
        <Label htmlFor="costing-sst-factor">SST factor</Label>
        <NumberInput
          id="costing-sst-factor"
          step="any"
          min={0}
          value={sst}
          disabled={!canManage}
          onChange={(e) => setSst(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="costing-default-method">Default cost method</Label>
        <SearchableSelect
          id="costing-default-method"
          aria-label="Default cost method"
          value={method}
          onChange={setMethod}
          options={METHOD_OPTIONS}
          disabled={!canManage}
        />
      </div>
      {problem ? (
        <p role="alert" className="text-sm text-destructive">
          {problem}
        </p>
      ) : null}
      {canManage ? (
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
      ) : null}
    </form>
  );
}

function SstTab() {
  const { data, isLoading, isError, error } = useCostingSettings();
  if (isError) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load the settings.'}
      </p>
    );
  }
  if (isLoading || !data) return null;
  return <SstForm settings={data} />;
}

// ------------------------------------------------------------------ Transport by category

interface RuleDraft {
  mode: string;
  value: string;
}

const draftOf = (rule: CategoryRule): RuleDraft => ({
  mode: rule.mode ?? '',
  value: rule.value === null ? '' : String(rule.value),
});

function RulesForm({ rules }: { rules: CategoryRule[] }) {
  const canManage = useHasPermission('products.party_costing.manage');
  const save = useSaveCategoryRule();
  const [drafts, setDrafts] = useState<Record<string, RuleDraft>>({});
  const current = (rule: CategoryRule) => drafts[rule.category_id] ?? draftOf(rule);
  const patch = (rule: CategoryRule, next: Partial<RuleDraft>) =>
    setDrafts((d) => ({ ...d, [rule.category_id]: { ...current(rule), ...next } }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const changed = rules.filter((r) => {
      const d = drafts[r.category_id];
      const base = draftOf(r);
      return !!d && (d.mode !== base.mode || d.value !== base.value);
    });
    const sends: { categoryId: string; mode: string | null; value: number | null }[] = [];
    for (const r of changed) {
      const d = drafts[r.category_id];
      if (!d.mode && d.value.trim() === '') {
        sends.push({ categoryId: r.category_id, mode: null, value: null });
        continue;
      }
      const value = positive(d.value);
      if (!d.mode || value === null) {
        toast.error(`${r.category_name}: pick Add or Multiply and a value above zero, or clear both.`);
        return;
      }
      sends.push({ categoryId: r.category_id, mode: d.mode, value });
    }
    try {
      for (const one of sends) await save.mutateAsync(one);
      if (sends.length) {
        toast.success('Transport rules saved');
        setDrafts({});
      }
    } catch {
      // The hook toasted the reason; what was typed stays.
    }
  };

  if (!rules.length) {
    return (
      <div className="rounded-lg border border-dashed py-6 text-center">
        <p className="text-sm font-medium">No categories yet</p>
      </div>
    );
  }
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4">
      <div className="overflow-x-auto rounded-lg border">
        <table aria-label="Transport by category" className="w-full text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className={TH}>Category</th>
              <th className={TH}>Mode</th>
              <th className={TH}>Value</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rules.map((rule) => {
              const d = current(rule);
              return (
                <tr key={rule.category_id}>
                  <td className="max-w-[14rem] px-3 py-2">
                    <span className="block truncate" title={rule.category_name}>
                      {rule.category_name}
                    </span>
                  </td>
                  <td className="w-44 px-3 py-1.5">
                    <SearchableSelect
                      aria-label={`Transport mode for ${rule.category_name}`}
                      value={d.mode}
                      onChange={(v) => patch(rule, { mode: v })}
                      options={MODE_OPTIONS}
                      placeholder="No rule"
                      clearable
                      disabled={!canManage}
                    />
                  </td>
                  <td className="w-32 px-3 py-1.5">
                    <NumberInput
                      aria-label={`Transport value for ${rule.category_name}`}
                      step="any"
                      min={0}
                      value={d.value}
                      disabled={!canManage}
                      onChange={(e) => patch(rule, { value: e.target.value })}
                      className="text-end"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {canManage ? (
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
      ) : null}
    </form>
  );
}

function RulesTab() {
  const { data, isLoading, isError, error } = useCategoryRules();
  if (isError) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load the transport rules.'}
      </p>
    );
  }
  if (isLoading || !data) return null;
  return <RulesForm rules={data.data} />;
}

// ------------------------------------------------------------------ the dialog

/**
 * Costing settings (AC-CG-13): dated exchange rates, the SST factor and default cost method, and
 * the transport rule of each category. Three line tabs; the rate form needs `scm.config.manage`,
 * the rest `products.party_costing.manage`.
 */
export function CostingSettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90dvh] w-[calc(100vw-2rem)] max-w-3xl flex-col" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Costing settings</DialogTitle>
          <DialogDescription className="sr-only">
            Exchange rates, SST and cost method, and transport by category.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto">
          <Tabs defaultValue="rates">
            <TabsList variant="line">
              <TabsTrigger value="rates">Exchange rates</TabsTrigger>
              <TabsTrigger value="sst">SST and method</TabsTrigger>
              <TabsTrigger value="transport">Transport by category</TabsTrigger>
            </TabsList>
            <TabsContent value="rates" className="pt-4">
              <RatesTab />
            </TabsContent>
            <TabsContent value="sst" className="pt-4">
              <SstTab />
            </TabsContent>
            <TabsContent value="transport" className="pt-4">
              <RulesTab />
            </TabsContent>
          </Tabs>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default CostingSettingsDialog;
