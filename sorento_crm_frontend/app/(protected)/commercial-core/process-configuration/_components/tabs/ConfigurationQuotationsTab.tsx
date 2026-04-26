'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { apiFetch } from '@/lib/api';
import { getProduct, getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import { SearchableSelect } from '@/app/(protected)/commercial/leads/components/SearchableSelect';
import {
  DEFAULT_QUOTATION_TEMPLATES,
  parseQuotationTemplates,
  QUOTATION_PACKAGE_TEMPLATES_KEY,
  type QuotationLine,
  type QuotationPackageTemplate,
} from '../../lib/quotationPackageTemplates';
import { getProcessSettings, patchProcessSettings, type ProcessSettings } from '../../services/processSettingsService';

function newId(): string {
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `qtpl-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function ConfigurationQuotationsTab() {
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: ['commercial-process-settings'],
    queryFn: getProcessSettings,
  });

  const parsed = useMemo(() => {
    const raw = settings?.assignment?.[QUOTATION_PACKAGE_TEMPLATES_KEY];
    const list = parseQuotationTemplates(raw);
    return list.length ? list : DEFAULT_QUOTATION_TEMPLATES;
  }, [settings?.assignment]);

  const [templates, setTemplates] = useState<QuotationPackageTemplate[]>(parsed);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    setTemplates(parsed);
    const deep = searchParams.get('qtpl');
    if (deep && parsed.some((t) => t.id === deep)) {
      setSelectedId(deep);
      return;
    }
    if (!selectedId || !parsed.some((t) => t.id === selectedId)) {
      setSelectedId(parsed[0]?.id ?? null);
    }
  }, [parsed, selectedId, searchParams]);

  const saveMut = useMutation({
    mutationFn: async (next: QuotationPackageTemplate[]) => {
      const cur =
        qc.getQueryData<ProcessSettings>(['commercial-process-settings']) ?? (await getProcessSettings());
      const assignment = { ...(cur.assignment ?? {}) };
      assignment[QUOTATION_PACKAGE_TEMPLATES_KEY] = next;
      return patchProcessSettings({ assignment });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-process-settings'] });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const persist = useCallback(
    (next: QuotationPackageTemplate[]) => {
      setTemplates(next);
      saveMut.mutate(next);
    },
    [saveMut],
  );

  const selected = templates.find((t) => t.id === selectedId) ?? null;

  const [termsOpen, setTermsOpen] = useState(false);
  const [validOpen, setValidOpen] = useState(false);
  const [itemOpen, setItemOpen] = useState(false);
  const [nameOpen, setNameOpen] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [termsDraft, setTermsDraft] = useState('');
  const [validDraft, setValidDraft] = useState('30');
  const [lineDraft, setLineDraft] = useState<Partial<QuotationLine>>({});
  const { data: productOptions = [], isLoading: productsLoading } = useQuery({
    queryKey: ['quotation-template-products-select'],
    queryFn: async () => {
      const rows = await getProducts({
        pageIndex: 0,
        pageSize: 200,
        sorting: [],
        searchQuery: '',
        status: 'active',
      });
      return rows.data.map((p) => ({
        id: p.id,
        label: `${p.product_name} (${p.product_code})`,
      }));
    },
  });
  const { data: uomOptions = [] } = useQuery({
    queryKey: ['quotation-template-uoms-select'],
    queryFn: async () => {
      const res = await apiFetch('/api/v1/master-data/units-of-measure/select');
      if (!res.ok) return [] as Array<{ code: string; label: string }>;
      const raw = (await res.json()) as Array<{ uom_code: string; uom_name: string }>;
      return (raw ?? []).map((r) => ({
        code: r.uom_code,
        label: r.uom_name ? `${r.uom_name} (${r.uom_code})` : r.uom_code,
      }));
    },
  });

  const updateSelected = useCallback(
    (fn: (t: QuotationPackageTemplate) => QuotationPackageTemplate) => {
      if (!selectedId) return;
      setTemplates((prev) => {
        const next = prev.map((t) => (t.id === selectedId ? fn(t) : t));
        saveMut.mutate(next);
        return next;
      });
    },
    [saveMut, selectedId],
  );

  if (isLoading && !settings) {
    return <Skeleton className="h-96 w-full rounded-[10px]" />;
  }

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <div className="w-full shrink-0 rounded-[10px] border border-[#e5e7eb] bg-white p-6 lg:w-[411px]">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-[#0a0a0a]">Templates</h3>
          <Button
            type="button"
            size="icon"
            variant="destructive"
            className="size-8 rounded-lg bg-[#e7000b] hover:bg-[#c90009]"
            onClick={() => {
              const n: QuotationPackageTemplate = {
                id: newId(),
                name: 'New package',
                validity_days: 30,
                terms: '',
                items: [],
              };
              persist([...templates, n]);
              setSelectedId(n.id);
            }}
          >
            <Plus className="size-4" />
          </Button>
        </div>
        <div className="flex flex-col gap-2">
          {templates.map((t) => {
            const active = t.id === selectedId;
            const summary = `${t.items.length} item${t.items.length === 1 ? '' : 's'} · ${t.validity_days} days validity`;
            return (
              <div
                key={t.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedId(t.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedId(t.id);
                  }
                }}
                className={cn(
                  'flex w-full items-start justify-between gap-2 rounded-lg border p-3 text-start',
                  active ? 'border-[#e7000b] bg-[#fef2f2]' : 'border-transparent hover:bg-muted/30',
                )}
              >
                <div>
                  <p className="text-sm font-medium text-[#0a0a0a]">{t.name}</p>
                  <p className="text-muted-foreground text-xs">{summary}</p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0 text-destructive hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!confirm(`Remove template “${t.name}”?`)) return;
                    const next = templates.filter((x) => x.id !== t.id);
                    persist(next);
                    setSelectedId(next[0]?.id ?? null);
                  }}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            );
          })}
        </div>
      </div>

      {!selected ? (
        <p className="text-muted-foreground text-sm">Select or create a template.</p>
      ) : (
        <div className="min-w-0 flex-1 space-y-6">
          <div className="rounded-[10px] border border-[#e5e7eb] bg-white">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e5e7eb] px-6 py-6">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-medium text-[#0a0a0a]">{selected.name}</h3>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => {
                      setNameDraft(selected.name);
                      setNameOpen(true);
                    }}
                    aria-label="Rename template"
                  >
                    <Pencil className="size-4" />
                  </Button>
                </div>
                <p className="text-muted-foreground text-sm">Configure quotation items</p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                className="rounded-lg bg-[#e7000b] hover:bg-[#c90009]"
                onClick={() => {
                  const line: QuotationLine = {
                    id: newId(),
                    product_id: '',
                    product_code: '',
                    name: '',
                    description: '',
                    quantity: 1,
                    uom: 'Unit',
                  };
                  setLineDraft(line);
                  setItemOpen(true);
                }}
              >
                <Plus className="size-4" />
                Add Item
              </Button>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-b bg-[#f9fafb]">
                    <TableHead className="text-[#364153]">Item</TableHead>
                    <TableHead className="text-[#364153]">Description</TableHead>
                    <TableHead className="w-[100px] text-[#364153]">Quantity</TableHead>
                    <TableHead className="w-[100px] text-[#364153]">UOM</TableHead>
                    <TableHead className="w-[100px] text-end text-[#364153]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {selected.items.map((line) => (
                    <TableRow key={line.id} className="border-b">
                      <TableCell className="font-medium text-[#e7000b]">{line.name || '—'}</TableCell>
                      <TableCell className="max-w-md text-[#364153]">{line.description || '—'}</TableCell>
                      <TableCell>{line.quantity}</TableCell>
                      <TableCell>{line.uom}</TableCell>
                      <TableCell className="text-end">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            setLineDraft(line);
                            setItemOpen(true);
                          }}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() =>
                            updateSelected((t) => ({
                              ...t,
                              items: t.items.filter((x) => x.id !== line.id),
                            }))
                          }
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="rounded-[10px] border border-[#e5e7eb] bg-white px-6 py-6">
            <div className="mb-4 flex items-center justify-between">
              <h4 className="text-base font-medium text-[#0a0a0a]">Terms & Conditions</h4>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => {
                  setTermsDraft(selected.terms);
                  setTermsOpen(true);
                }}
              >
                <Pencil className="size-4" />
              </Button>
            </div>
            <p className="text-[#364153] text-sm">{selected.terms || '—'}</p>
          </div>

          <div className="rounded-[10px] border border-[#e5e7eb] bg-white px-6 py-6">
            <div className="mb-4 flex items-center justify-between">
              <h4 className="text-base font-medium text-[#0a0a0a]">Quotation Validity</h4>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => {
                  setValidDraft(String(selected.validity_days));
                  setValidOpen(true);
                }}
              >
                <Pencil className="size-4" />
              </Button>
            </div>
            <p className="text-[#364153] text-sm">Valid for {selected.validity_days} days</p>
          </div>
        </div>
      )}

      <Dialog open={termsOpen} onOpenChange={setTermsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Terms & Conditions</DialogTitle>
          </DialogHeader>
          <Textarea value={termsDraft} onChange={(e) => setTermsDraft(e.target.value)} rows={5} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setTermsOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                updateSelected((t) => ({ ...t, terms: termsDraft }));
                setTermsOpen(false);
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={nameOpen} onOpenChange={setNameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename template</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label>Name</Label>
            <Input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setNameOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!nameDraft.trim()}
              onClick={() => {
                updateSelected((t) => ({ ...t, name: nameDraft.trim() }));
                setNameOpen(false);
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={validOpen} onOpenChange={setValidOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Quotation validity (days)</DialogTitle>
          </DialogHeader>
          <Input type="number" min={1} value={validDraft} onChange={(e) => setValidDraft(e.target.value)} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setValidOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                const n = parseInt(validDraft, 10) || 30;
                updateSelected((t) => ({ ...t, validity_days: n }));
                setValidOpen(false);
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={itemOpen} onOpenChange={setItemOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Line item</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label>Product</Label>
                <SearchableSelect
                  value={lineDraft.product_id || ''}
                  onValueChange={async (v) => {
                    const picked = productOptions.find((p) => p.id === v);
                    const fallbackName = picked ? picked.label.split(' (')[0] : '';
                    try {
                      const detail = await getProduct(v);
                      setLineDraft((d) => ({
                        ...d,
                        product_id: v,
                        product_code: detail.product_code || '',
                        name: detail.product_name || fallbackName,
                        description: (detail.description || detail.product_name || fallbackName || '').trim(),
                        uom: detail.base_uom?.uom_code || d.uom || '',
                      }));
                    } catch {
                      setLineDraft((d) => ({
                        ...d,
                        product_id: v,
                        name: fallbackName,
                      }));
                    }
                  }}
                  options={productOptions.map((p) => ({ value: p.id, label: p.label }))}
                  placeholder={productsLoading ? 'Loading products…' : 'Select product'}
                />
            </div>
            <div className="grid gap-2">
              <Label>Description</Label>
              <Input
                value={lineDraft.description ?? ''}
                onChange={(e) => setLineDraft((d) => ({ ...d, description: e.target.value }))}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>Quantity</Label>
                <Input
                  type="number"
                  value={lineDraft.quantity ?? 0}
                  onChange={(e) => setLineDraft((d) => ({ ...d, quantity: Number(e.target.value) }))}
                />
              </div>
              <div className="grid gap-2">
                <Label>UOM</Label>
                <SearchableSelect
                  value={lineDraft.uom ?? ''}
                  onValueChange={(v) => setLineDraft((d) => ({ ...d, uom: v }))}
                  options={uomOptions.map((u) => ({ value: u.code, label: u.label }))}
                  placeholder="Select UOM"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setItemOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!lineDraft.product_id}
              onClick={() => {
                if (!lineDraft.id) return;
                const lineId = lineDraft.id;
                const savedName = (lineDraft.name || '').trim() || 'Product';
                updateSelected((t) => ({
                  ...t,
                  items: t.items.some((x) => x.id === lineId)
                    ? t.items.map((x) =>
                        x.id === lineId
                          ? {
                              ...x,
                              product_id: lineDraft.product_id || '',
                              product_code: (lineDraft.product_code ?? '').trim(),
                              name: savedName,
                              description: (lineDraft.description ?? '').trim(),
                              quantity: lineDraft.quantity ?? 0,
                              uom: (lineDraft.uom ?? 'Unit').trim(),
                            }
                          : x,
                      )
                    : [
                        ...t.items,
                        {
                          id: lineId,
                          product_id: lineDraft.product_id || '',
                          product_code: (lineDraft.product_code ?? '').trim(),
                          name: savedName,
                          description: (lineDraft.description ?? '').trim(),
                          quantity: lineDraft.quantity ?? 0,
                          uom: (lineDraft.uom ?? 'Unit').trim(),
                        },
                      ],
                }));
                setItemOpen(false);
                setLineDraft({});
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
