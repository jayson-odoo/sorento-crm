'use client';

import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { LeadRefItem, parseLeadRefItems, toAssignmentPayload } from '../../lib/referenceAssignment';
import { getProcessSettings, patchProcessSettings, type ProcessSettings } from '../../services/processSettingsService';

export type ReferenceSubTab =
  | 'countries'
  | 'states'
  | 'budget'
  | 'closure'
  | 'property'
  | 'sources'
  | 'contact';

const REF_ORDER: ReferenceSubTab[] = [
  'countries',
  'states',
  'budget',
  'closure',
  'property',
  'sources',
  'contact',
];

const ASSIGN_KEY: Record<ReferenceSubTab, string> = {
  countries: 'lead_countries',
  states: 'lead_states',
  budget: 'lead_budget_ranges',
  closure: 'lead_sales_closure_confidence',
  property: 'lead_property_types',
  sources: 'lead_sources',
  contact: 'lead_contact_methods',
};

const REF_LABEL: Record<ReferenceSubTab, string> = {
  countries: 'Countries',
  states: 'States',
  budget: 'Budget Range',
  closure: 'Closure Confidence',
  property: 'Property Types',
  sources: 'Lead Sources',
  contact: 'Contact Methods',
};

function ActivePill({ active }: { active: boolean }) {
  if (!active) return <span className="text-muted-foreground text-sm">Inactive</span>;
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-[12px] font-medium text-emerald-900">
      Active
    </span>
  );
}

export function ConfigurationReferenceDataTab({ sub }: { sub: ReferenceSubTab }) {
  const qc = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: ['commercial-process-settings'],
    queryFn: getProcessSettings,
  });

  const rowsByKey = useMemo(() => {
    const ass = settings?.assignment ?? {};
    const map: Partial<Record<ReferenceSubTab, LeadRefItem[]>> = {};
    for (const id of REF_ORDER) {
      map[id] = parseLeadRefItems(ass[ASSIGN_KEY[id]]);
    }
    return map;
  }, [settings?.assignment]);

  const countries = rowsByKey.countries ?? [];

  const saveKey = useMutation({
    mutationFn: async ({ key, rows }: { key: string; rows: LeadRefItem[] }) => {
      const cur =
        qc.getQueryData<ProcessSettings>(['commercial-process-settings']) ?? (await getProcessSettings());
      const assignment = { ...(cur.assignment ?? {}) };
      assignment[key] = toAssignmentPayload(rows);
      return patchProcessSettings({ assignment });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-process-settings'] });
      void qc.invalidateQueries({ queryKey: ['lead-assignment-select'] });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const persist = useCallback(
    (refId: ReferenceSubTab, rows: LeadRefItem[]) => {
      saveKey.mutate({ key: ASSIGN_KEY[refId], rows });
    },
    [saveKey],
  );

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [order, setOrder] = useState('1');
  const [countryCode, setCountryCode] = useState('');
  const [active, setActive] = useState(true);

  const rows = rowsByKey[sub] ?? [];

  const openAdd = () => {
    setEditingIdx(null);
    setCode('');
    setName('');
    setOrder(String((rows.length || 0) + 1));
    setCountryCode(countries[0]?.code ?? '');
    setActive(true);
    setDialogOpen(true);
  };

  const openEdit = (idx: number) => {
    const r = rows[idx];
    if (!r) return;
    setEditingIdx(idx);
    setCode(r.code);
    setName(r.label);
    setOrder(String(r.sort_order ?? idx + 1));
    setCountryCode(r.country_code ?? countries[0]?.code ?? '');
    setActive(r.is_active);
    setDialogOpen(true);
  };

  const saveRow = () => {
    const c = code.trim();
    const n = name.trim();
    if (!c || !n) {
      toast.error('Code and name are required');
      return;
    }
    const item: LeadRefItem = {
      code: c,
      label: n,
      is_active: active,
    };
    if (sub === 'states' && countryCode) item.country_code = countryCode.trim();
    if (sub === 'budget' || sub === 'closure') {
      item.sort_order = parseInt(order, 10) || 0;
    }

    let next: LeadRefItem[];
    if (editingIdx === null) {
      next = [...rows, item];
    } else {
      next = rows.map((x, i) => (i === editingIdx ? { ...item, code: x.code } : x));
    }

    persist(sub, next);
    setDialogOpen(false);
  };

  const deleteRow = (idx: number) => {
    if (!confirm('Remove this row?')) return;
    persist(
      sub,
      rows.filter((_, i) => i !== idx),
    );
  };

  const countryLabel = (codeStr: string) => countries.find((c) => c.code === codeStr)?.label ?? codeStr;

  const addLabel =
    sub === 'countries'
      ? 'Add Country'
      : sub === 'states'
        ? 'Add State'
        : sub === 'budget'
          ? 'Add Budget Range'
          : sub === 'closure'
            ? 'Add Closure Confidence'
            : sub === 'property'
              ? 'Add Property Type'
              : sub === 'sources'
                ? 'Add Lead Source'
                : 'Add Contact Method';

  const description =
    sub === 'countries'
      ? 'Manage countries for the system'
      : sub === 'states'
        ? 'Manage states for the system'
        : sub === 'budget'
          ? 'Manage budget range for the system'
          : sub === 'closure'
            ? 'Manage closure confidence for the system'
            : sub === 'property'
              ? 'Manage property types for the system'
              : sub === 'sources'
                ? 'Manage lead sources for the system'
                : 'Manage contact methods for the system';

  if (isLoading && !settings) {
    return <Skeleton className="h-72 w-full rounded-[10px]" />;
  }

  return (
    <div className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white">
      <div className="flex flex-wrap border-b border-[#e5e7eb]">
        {REF_ORDER.map((id) => (
          <Link
            key={id}
            href={`/commercial-core/process-configuration?tab=reference&ref=${id}`}
            className={cn(
              'border-b-2 px-4 py-3 text-sm font-medium transition-colors',
              sub === id ? 'border-[#e7000b] text-[#e7000b]' : 'border-transparent text-[#4a5565] hover:text-foreground',
            )}
          >
            {REF_LABEL[id]}
          </Link>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e5e7eb] px-6 py-6">
        <div>
          <h3 className="text-lg font-medium text-[#0a0a0a]">{REF_LABEL[sub]}</h3>
          <p className="text-muted-foreground text-sm">{description}</p>
        </div>
        <Button
          type="button"
          variant="destructive"
          className="rounded-lg bg-[#e7000b] hover:bg-[#c90009]"
          onClick={openAdd}
        >
          <Plus className="size-4" />
          {addLabel}
        </Button>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-b bg-[#f9fafb]">
              <TableHead className="font-medium text-[#364153]">Code</TableHead>
              <TableHead className="font-medium text-[#364153]">Name</TableHead>
              {sub === 'states' ? <TableHead className="font-medium text-[#364153]">Country</TableHead> : null}
              {sub === 'budget' || sub === 'closure' ? (
                <TableHead className="font-medium text-[#364153]">Order</TableHead>
              ) : null}
              <TableHead className="text-center font-medium text-[#364153]">Active</TableHead>
              <TableHead className="text-end font-medium text-[#364153]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, idx) => (
              <TableRow key={`${r.code}-${idx}`} className="border-b border-[#e5e7eb]">
                <TableCell className="font-medium text-[#e7000b]">{r.code}</TableCell>
                <TableCell className="text-[#364153]">{r.label}</TableCell>
                {sub === 'states' ? (
                  <TableCell className="text-[#364153]">{r.country_code ? countryLabel(r.country_code) : '—'}</TableCell>
                ) : null}
                {sub === 'budget' || sub === 'closure' ? <TableCell>{r.sort_order ?? '—'}</TableCell> : null}
                <TableCell className="text-center">
                  <ActivePill active={r.is_active} />
                </TableCell>
                <TableCell className="text-end">
                  <Button type="button" variant="ghost" size="icon" aria-label="Edit" onClick={() => openEdit(idx)}>
                    <Pencil className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="text-destructive hover:text-destructive"
                    aria-label="Delete"
                    onClick={() => deleteRow(idx)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingIdx === null ? addLabel : 'Edit row'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label>Code</Label>
              <Input value={code} onChange={(e) => setCode(e.target.value)} disabled={editingIdx !== null} />
            </div>
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            {sub === 'states' ? (
              <div className="grid gap-2">
                <Label>Country</Label>
                <Select value={countryCode || '__none__'} onValueChange={(v) => setCountryCode(v === '__none__' ? '' : v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select country" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">—</SelectItem>
                    {countries.map((c) => (
                      <SelectItem key={c.code} value={c.code}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            {sub === 'budget' || sub === 'closure' ? (
              <div className="grid gap-2">
                <Label>Order</Label>
                <Input type="number" value={order} onChange={(e) => setOrder(e.target.value)} />
              </div>
            ) : null}
            <div className="flex items-center justify-between gap-4">
              <Label>Active</Label>
              <Switch checked={active} onCheckedChange={setActive} />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={saveRow}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
