'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Container } from '@/components/common/container';
import { TruncatedTextCell } from '@/components/common/TruncatedTextCell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { QuotationReactQuill } from '@/components/commercial/QuotationReactQuill';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { ArrowLeft, Loader2 } from 'lucide-react';
import {
  applyMasterQuotationPackageTemplate,
  getCommercialProject,
} from '@/app/(protected)/commercial-management/projects/services/commercialProjectService';
import { getCustomer } from '@/app/(protected)/order-management/customers/services/customerService';
import { parseClientNotesMeta } from '@/app/(protected)/order-management/customers/lib/client-notes';
import { useCustomerSelectQuery } from '@/app/(protected)/order-management/shared/hooks/use-customer-select-query';
import {
  parseQuotationTemplates,
  QUOTATION_PACKAGE_TEMPLATES_KEY,
  type QuotationPackageTemplate,
} from '@/app/(protected)/commercial-core/process-configuration/lib/quotationPackageTemplates';
import { getProcessSettings } from '@/app/(protected)/commercial-core/process-configuration/services/processSettingsService';
import { getProductAttachmentsByProduct } from '@/app/(protected)/master-data-management/product-attachments/services/productAttachmentService';
import {
  filterProductImageAttachments,
  filterTechnicalSpecAttachments,
} from '@/app/(protected)/commercial-management/quotation-revisions/lib/quotationProductImages';
import { getProduct, getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import type { ProductDetail } from '@/app/(protected)/master-data-management/products/types/product.types';
import {
  formatOrderLineMoney,
  OrderLinesEditor,
  orderLinesTotals,
  type DiscountMode,
  type OrderLineRowData,
} from './OrderLinesEditor';
import { cn } from '@/lib/utils';
import { EntityActivitiesDock } from '@/app/(protected)/commercial-management/shared/components/EntityActivitiesDock';

const CM = '/api/commercial-management';

type SelectOpt = { code: string; label: string };

type QuotationStage = { stage_code: string; stage_name: string; is_terminal?: boolean };

type MasterDetail = {
  id: string;
  project_id?: string | null;
  customer_id?: string | null;
  tender_code: string;
  quotation_code: string;
  quotation_stage?: QuotationStage | null;
  current_working_revision_id?: string | null;
  quoted_currency?: string | null;
  quotation_package_template_id?: string | null;
  quotation_package_template_name?: string | null;
};

type RevisionRow = {
  id: string;
  revision_number: number;
  pricing_snapshot: Record<string, unknown>;
};

function newLineKey(): string {
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function parseDiscountFromRow(r: Record<string, unknown>): {
  discount_mode: DiscountMode;
  discount_value: string;
} {
  const pct = String(r.discount_pct ?? r.discount_percent ?? '').trim();
  const amt = String(r.discount_amt ?? r.discount_amount ?? '').trim();
  const modeRaw = r.discount_mode;
  if (modeRaw === 'percent') {
    return { discount_mode: 'percent', discount_value: pct };
  }
  if (modeRaw === 'amount') {
    return { discount_mode: 'amount', discount_value: amt };
  }
  if (pct !== '' && amt === '') return { discount_mode: 'percent', discount_value: pct };
  if (amt !== '' && pct === '') return { discount_mode: 'amount', discount_value: amt };
  if (pct !== '' && amt !== '') return { discount_mode: 'percent', discount_value: pct };
  return { discount_mode: 'percent', discount_value: '' };
}

function emptyMeta() {
  return {
    customer_id: '',
    seller_reference: '',
    customer_reference: '',
    customer_label: '',
    customer_address: '',
    customer_pic_name: '',
    customer_phone: '',
    customer_email: '',
    customer_attention_to: '',
    issued_on: '',
    salesperson_user_id: '',
    payment_term_code: '',
    notes: '',
    terms_html: '',
    quotation_validity_days: '',
    quotation_package_template_id: '',
    quotation_package_template_name: '',
    task_template_id: '',
    task_template_name: '',
  };
}

function parseAttachmentIds(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => String(x)).filter(Boolean);
}

function parseSnapshot(snap: Record<string, unknown> | undefined) {
  const metaRaw = snap?.quotation_meta;
  const meta =
    typeof metaRaw === 'object' && metaRaw !== null ? { ...emptyMeta(), ...(metaRaw as Record<string, string>) } : emptyMeta();
  const itemsRaw = snap?.order_items;
  const lines: OrderLineRowData[] = [];
  if (Array.isArray(itemsRaw)) {
    for (const row of itemsRaw) {
      if (!row || typeof row !== 'object') continue;
      const r = row as Record<string, unknown>;
      lines.push({
        _key: typeof r._key === 'string' && r._key ? String(r._key) : newLineKey(),
        product_id: String(r.product_id ?? ''),
        product_code: r.product_code != null ? String(r.product_code) : '',
        brand: r.brand != null ? String(r.brand) : '',
        description: r.description != null ? String(r.description) : '',
        product_image_attachment_ids: parseAttachmentIds(r.product_image_attachment_ids),
        technical_spec_attachment_ids: parseAttachmentIds(r.technical_spec_attachment_ids),
        is_optional: Boolean(r.is_optional),
        qty: String(r.qty ?? r.quantity ?? '1'),
        uom_code: String(r.uom_code ?? ''),
        unit_price: String(r.unit_price ?? '0'),
        ...parseDiscountFromRow(r),
        tax_rate_code: String(r.tax_rate_code ?? ''),
      });
    }
  }
  return { meta, lines };
}

function buildSnapshot(meta: ReturnType<typeof emptyMeta>, lines: OrderLineRowData[]): Record<string, unknown> {
  return {
    quotation_meta: {
      customer_id: meta.customer_id,
      seller_reference: meta.seller_reference,
      customer_reference: meta.customer_reference,
      customer_label: meta.customer_label,
      customer_address: meta.customer_address,
      customer_pic_name: meta.customer_pic_name,
      customer_phone: meta.customer_phone,
      customer_email: meta.customer_email,
      customer_attention_to: meta.customer_attention_to,
      issued_on: meta.issued_on,
      salesperson_user_id: meta.salesperson_user_id,
      payment_term_code: meta.payment_term_code,
      notes: meta.notes,
      terms_html: meta.terms_html,
      quotation_validity_days: meta.quotation_validity_days,
      quotation_package_template_id: meta.quotation_package_template_id,
      quotation_package_template_name: meta.quotation_package_template_name,
      task_template_id: meta.task_template_id,
      task_template_name: meta.task_template_name,
    },
    order_items: lines.map((l) => ({
      _key: l._key,
      product_id: l.product_id,
      product_code: l.product_code,
      brand: l.brand,
      description: l.description,
      product_image_attachment_ids:
        l.product_image_attachment_ids && l.product_image_attachment_ids.length > 0
          ? l.product_image_attachment_ids
          : undefined,
      technical_spec_attachment_ids:
        l.technical_spec_attachment_ids && l.technical_spec_attachment_ids.length > 0
          ? l.technical_spec_attachment_ids
          : undefined,
      is_optional: l.is_optional ? true : undefined,
      qty: l.qty,
      uom_code: l.uom_code,
      unit_price: l.unit_price,
      discount_pct: l.discount_mode === 'percent' ? l.discount_value : '',
      discount_amt: l.discount_mode === 'amount' ? l.discount_value : '',
      discount_mode: l.discount_mode,
      tax_rate_code: l.tax_rate_code,
    })),
  };
}

function formatBillingAddress(a: Record<string, unknown> | null | undefined): string {
  if (!a || typeof a !== 'object') return '';
  const parts = ['line_1', 'line_2', 'postcode', 'city', 'state', 'country']
    .map((k) => {
      const v = a[k];
      return typeof v === 'string' ? v.trim() : '';
    })
    .filter(Boolean);
  return parts.join(', ');
}

export default function QuotationEditPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status } = useSession();
  const canEditMaster = useHasPermission('commercial_core.master_quotations.edit');
  const canEditRevision = useHasPermission('commercial_core.quotation_revisions.edit');

  const tenderCode = (searchParams.get('tender') || '').trim();
  const quotationCode = (searchParams.get('quotation') || '').trim();
  const projectFromUrl = searchParams.get('project');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [master, setMaster] = useState<MasterDetail | null>(null);
  const [workingRevisionId, setWorkingRevisionId] = useState<string | null>(null);
  const [meta, setMeta] = useState(() => emptyMeta());
  const [lines, setLines] = useState<OrderLineRowData[]>([]);
  const [editTab, setEditTab] = useState<'orderLines' | 'internalNotes'>('orderLines');

  const [paymentTerms, setPaymentTerms] = useState<SelectOpt[]>([]);
  const [uoms, setUoms] = useState<SelectOpt[]>([]);
  const [taxRates, setTaxRates] = useState<SelectOpt[]>([]);
  const [users, setUsers] = useState<{ id: string; name: string | null; email: string }[]>([]);
  const [confirmPkgOpen, setConfirmPkgOpen] = useState(false);
  const [pendingPkgId, setPendingPkgId] = useState<string | null>(null);
  const [replacingPkg, setReplacingPkg] = useState(false);
  const [pkgSelectId, setPkgSelectId] = useState('');
  const [showEditUnitCost, setShowEditUnitCost] = useState(true);

  const viewHref = useMemo(() => {
    const p = new URLSearchParams();
    p.set('tender', tenderCode);
    p.set('quotation', quotationCode);
    if (projectFromUrl) p.set('project', projectFromUrl);
    return `/commercial-management/quotation-revisions?${p.toString()}`;
  }, [tenderCode, quotationCode, projectFromUrl]);

  const effectiveProjectId = master?.project_id || projectFromUrl || '';

  const { data: projectCtx } = useQuery({
    queryKey: ['commercial-project-ctx', effectiveProjectId],
    queryFn: () => getCommercialProject(effectiveProjectId),
    enabled: Boolean(effectiveProjectId && master),
  });
  const { data: customerOptions = [], isPending: customersLoading } = useCustomerSelectQuery({
    enabled: Boolean(master),
  });
  const customerIdForQuotation = (meta.customer_id || master?.customer_id || projectCtx?.customer_id || '').trim();
  const { data: customerCtx } = useQuery({
    queryKey: ['quotation-customer-ctx', customerIdForQuotation],
    queryFn: () => getCustomer(customerIdForQuotation),
    enabled: Boolean(customerIdForQuotation),
  });

  const { data: processSettings } = useQuery({
    queryKey: ['commercial-process-settings', 'quotation-edit'],
    queryFn: getProcessSettings,
    enabled: Boolean(master),
  });

  const packageTemplates: QuotationPackageTemplate[] = useMemo(() => {
    const raw = processSettings?.assignment?.[QUOTATION_PACKAGE_TEMPLATES_KEY];
    return parseQuotationTemplates(raw);
  }, [processSettings?.assignment]);

  const orderLinesMoneyTotals = useMemo(() => orderLinesTotals(lines), [lines]);

  useEffect(() => {
    if (!customerCtx) return;
    const nmeta = parseClientNotesMeta(customerCtx.notes);
    const customerAddress = formatBillingAddress(customerCtx.billing_address);
    setMeta((prev) => ({
      ...prev,
      customer_id: customerCtx.id,
      customer_label: customerCtx.customer_name || '',
      customer_address: customerAddress,
      customer_phone: customerCtx.phone_number || '',
      customer_email: customerCtx.email || '',
      customer_pic_name: nmeta.picName || '',
      customer_attention_to: nmeta.picName || '',
    }));
  }, [customerCtx]);

  const loadSelects = useCallback(async () => {
    const [ptRes, txRes, uomRes, uRes] = await Promise.all([
      apiFetch('/api/v1/commercial/process-config/settings/payment-terms/select'),
      apiFetch('/api/v1/commercial/process-config/settings/tax-rates/select'),
      apiFetch('/api/v1/master-data/units-of-measure/select'),
      apiFetch('/api/user-management/users/select'),
    ]);
    if (ptRes.ok) {
      const j = (await ptRes.json()) as { data: SelectOpt[] };
      setPaymentTerms(j.data ?? []);
    }
    if (txRes.ok) {
      const j = (await txRes.json()) as { data: SelectOpt[] };
      setTaxRates(j.data ?? []);
    }
    if (uomRes.ok) {
      const raw = (await uomRes.json()) as Array<{ uom_code: string; uom_name: string }>;
      setUoms(
        (raw ?? []).map((r) => ({
          code: r.uom_code,
          label: r.uom_name ? `${r.uom_name} (${r.uom_code})` : r.uom_code,
        })),
      );
    }
    if (uRes.ok) {
      const raw = await uRes.json().catch(() => []);
      const arr = Array.isArray(raw) ? raw : (raw as { data?: unknown[] })?.data;
      if (Array.isArray(arr)) {
        setUsers(
          arr
            .map((x: unknown) => {
              const o = x as Record<string, unknown>;
              return {
                id: String(o.id ?? o.user_id ?? ''),
                name: (o.name as string) ?? null,
                email: String(o.email ?? ''),
              };
            })
            .filter((u) => u.id),
        );
      }
    }
  }, []);

  const fetchProductOptions = useCallback(async (query: string, pageIndex: number) => {
    const res = await getProducts({
      pageIndex,
      pageSize: 50,
      searchQuery: query || undefined,
      status: 'active',
    });
    return {
      data: res.data.map((p) => ({
        id: p.id,
        product_code: p.product_code,
        product_name: p.product_name,
      })),
    };
  }, []);

  const load = useCallback(async () => {
    if (!tenderCode || !quotationCode) return;
    setLoading(true);
    try {
      const encT = encodeURIComponent(tenderCode);
      const encQ = encodeURIComponent(quotationCode);
      const dRes = await apiFetch(`${CM}/tenders/by-code/${encT}/master-quotations/by-code/${encQ}`);
      if (!dRes.ok) {
        toast.error('Could not load this quotation.');
        router.push(viewHref);
        return;
      }
      const detail = (await dRes.json()) as MasterDetail;
      if (detail.quotation_stage?.is_terminal) {
        toast.message('This quotation is in a final stage and cannot be edited.');
        router.replace(viewHref);
        return;
      }
      setMaster(detail);

      const wid = detail.current_working_revision_id;
      if (!wid) {
        toast.error('No working revision to edit.');
        router.replace(viewHref);
        return;
      }
      setWorkingRevisionId(wid);

      const rRes = await apiFetch(`${CM}/quotation-revisions/${wid}`);
      if (!rRes.ok) {
        toast.error('Could not load working revision.');
        router.replace(viewHref);
        return;
      }
      const rev = (await rRes.json()) as RevisionRow;
      const { meta: m, lines: ln } = parseSnapshot(rev.pricing_snapshot as Record<string, unknown>);
      setMeta(m);
      setLines(ln.length ? ln : []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load quotation.');
      router.replace(viewHref);
    } finally {
      setLoading(false);
    }
  }, [quotationCode, tenderCode, router, viewHref]);

  useEffect(() => {
    void loadSelects();
  }, [loadSelects]);

  useEffect(() => {
    if (status === 'authenticated') {
      void load();
    }
  }, [status, load]);

  useEffect(() => {
    if (status === 'authenticated' && (!canEditMaster || !canEditRevision)) {
      toast.error('You do not have permission to edit this quotation.');
      router.replace(viewHref);
    }
  }, [canEditMaster, canEditRevision, router, status, viewHref]);

  useEffect(() => {
    setPkgSelectId(master?.quotation_package_template_id?.trim() || '');
  }, [master?.quotation_package_template_id]);

  useEffect(() => {
    if (!pkgSelectId) return;
    const exists = packageTemplates.some((tpl) => tpl.id === pkgSelectId);
    if (!exists) setPkgSelectId('');
  }, [pkgSelectId, packageTemplates]);

  const confirmPkgApply = useCallback(async () => {
    if (!master?.id || !pendingPkgId) return;
    setReplacingPkg(true);
    try {
      await applyMasterQuotationPackageTemplate(master.id, pendingPkgId);
      toast.success('Quotation template applied.');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to apply template.');
    } finally {
      setReplacingPkg(false);
      setConfirmPkgOpen(false);
      setPendingPkgId(null);
    }
  }, [master?.id, pendingPkgId, load]);

  const projectLabel = projectCtx?.title || '—';

  const missingClient = !customerIdForQuotation;
  const missingProject = projectLabel === '—';
  const missingOrderDate = !meta.issued_on?.trim();
  const missingValidity = !meta.quotation_validity_days?.trim();
  const missingPayment = !meta.payment_term_code?.trim();
  const missingSales = !meta.salesperson_user_id?.trim();

  const productIdsForLines = useMemo(
    () => Array.from(new Set(lines.map((l) => l.product_id).filter(Boolean))) as string[],
    [lines],
  );
  const productQueries = useQueries({
    queries: productIdsForLines.map((id) => ({
      queryKey: ['master-product-detail', id],
      queryFn: () => getProduct(id),
      enabled: Boolean(id),
      staleTime: 60_000,
    })),
  });
  const productById = useMemo(() => {
    const m = new Map<string, ProductDetail>();
    productIdsForLines.forEach((id, i) => {
      const d = productQueries[i]?.data;
      if (d) m.set(id, d);
    });
    return m;
  }, [productIdsForLines, productQueries]);

  const orderLinesCostTotal = useMemo(() => {
    let t = 0;
    for (const l of lines) {
      if (l.is_optional) continue;
      if (!l.product_id) continue;
      const p = productById.get(l.product_id);
      if (p?.cost_price == null) continue;
      const c = Number(p.cost_price);
      if (Number.isNaN(c)) continue;
      t += (Number(l.qty) || 0) * c;
    }
    return t;
  }, [lines, productById]);

  const editMarginAmt = orderLinesMoneyTotals.subtotal - orderLinesCostTotal;
  const editMarginPct =
    orderLinesMoneyTotals.subtotal > 0 ? (editMarginAmt / orderLinesMoneyTotals.subtotal) * 100 : 0;
  const editHasCostData = lines.some((l) => {
    const p = l.product_id ? productById.get(l.product_id) : undefined;
    return p?.cost_price != null && !Number.isNaN(Number(p.cost_price));
  });

  const updateLine = useCallback((key: string, patch: Partial<OrderLineRowData>) => {
    setLines((prev) => prev.map((l) => (l._key === key ? { ...l, ...patch } : l)));
  }, []);

  const moveLine = useCallback((fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return;
    setLines((prev) => {
      const next = [...prev];
      const [removed] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, removed);
      return next;
    });
  }, []);

  const removeLine = useCallback((key: string) => {
    setLines((prev) => prev.filter((l) => l._key !== key));
  }, []);

  const addLine = useCallback((isOptional = false) => {
    setLines((prev) => [
      ...prev,
      {
        _key: newLineKey(),
        product_id: '',
        product_code: '',
        brand: '',
        description: '',
        product_image_attachment_ids: [],
        technical_spec_attachment_ids: [],
        is_optional: isOptional,
        qty: '1',
        uom_code: '',
        unit_price: '0',
        discount_mode: 'percent',
        discount_value: '',
        tax_rate_code: '',
      },
    ]);
  }, []);

  const onPickProduct = useCallback(
    async (lineKey: string, productId: string) => {
      if (!productId) {
        updateLine(lineKey, {
          product_id: '',
          product_code: '',
          brand: '',
          product_image_attachment_ids: [],
          technical_spec_attachment_ids: [],
        });
        return;
      }
      try {
        const p = await getProduct(productId);
        const uom = p.base_uom?.uom_code || '';
        let defaultImgIds: string[] = [];
        let defaultTechSpecIds: string[] = [];
        try {
          const pas = await getProductAttachmentsByProduct(productId);
          const imgs = filterProductImageAttachments(pas);
          const specs = filterTechnicalSpecAttachments(pas);
          if (imgs[0]?.attachment_id) defaultImgIds = [imgs[0].attachment_id];
          defaultTechSpecIds = specs
            .map((x) => x.attachment_id?.trim())
            .filter((x): x is string => Boolean(x));
        } catch {
          defaultImgIds = [];
          defaultTechSpecIds = [];
        }
        updateLine(lineKey, {
          product_id: productId,
          product_code: p.product_code,
          brand: p.brand?.brand_name || '',
          description: p.description ? String(p.description) : p.product_name,
          unit_price: String(p.list_price ?? 0),
          uom_code: uom || undefined,
          product_image_attachment_ids: defaultImgIds,
          technical_spec_attachment_ids: defaultTechSpecIds,
        });
      } catch {
        updateLine(lineKey, { product_id: productId, product_image_attachment_ids: [], technical_spec_attachment_ids: [] });
      }
    },
    [updateLine],
  );

  const cancel = () => {
    router.push(viewHref);
  };

  const save = async () => {
    if (!master || !workingRevisionId) return;
    setSaving(true);
    try {
      const res = await apiFetch(`${CM}/quotation-revisions/${workingRevisionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pricing_snapshot: buildSnapshot(meta, lines) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error((err as { detail?: string }).detail || 'Save failed.');
        return;
      }
      toast.success('Quotation saved.');
      router.push(viewHref);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  if (status === 'loading' || loading) {
    return (
      <Container width="fluid">
        <div className="flex items-center gap-2 py-10 text-muted-foreground text-sm">
          <Loader2 className="size-4 animate-spin" />
          Loading…
        </div>
      </Container>
    );
  }

  if (!tenderCode || !quotationCode) {
    return (
      <Container width="fluid">
        <p className="text-muted-foreground py-6 text-sm">Missing tender or quotation in the URL.</p>
        <Button asChild variant="outline">
          <Link href="/commercial-management/quotations">Back to quotations</Link>
        </Button>
      </Container>
    );
  }

  return (
    <Container width="fluid">
      <div className="mt-2 space-y-6">
        <div className="flex flex-col gap-4 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <Button type="button" variant="ghost" size="icon" className="mt-0.5 shrink-0" asChild>
              <Link href={viewHref} aria-label="Back to quotation">
                <ArrowLeft className="size-5" />
              </Link>
            </Button>
            <div className="min-w-0">
              <h1 className="text-2xl font-medium tracking-tight text-[#0a0a0a]">
                Edit Quotation: {master?.quotation_code ?? quotationCode}
              </h1>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <Button type="button" variant="outline" onClick={cancel}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-[#e7000b] text-white hover:bg-[#e7000b]/90"
              disabled={saving || !master}
              onClick={() => void save()}
            >
              {saving ? <Loader2 className="me-2 size-4 animate-spin" /> : null}
              Save changes
            </Button>
          </div>
        </div>

        <div className="rounded-2xl border border-[#e5e7eb] bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-[#0a0a0a]">Quotation Information</h2>
          <div className="grid gap-6 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Client</Label>
              <Select
                value={customerIdForQuotation || '__none__'}
                onValueChange={(v) => {
                  const nextId = v === '__none__' ? '' : v;
                  const option = customerOptions.find((c) => c.id === nextId);
                  setMeta((m) => ({
                    ...m,
                    customer_id: nextId,
                    customer_label: option?.customer_name || '',
                    customer_address: '',
                    customer_pic_name: '',
                    customer_attention_to: '',
                    customer_phone: '',
                    customer_email: '',
                  }));
                }}
                disabled={customersLoading}
              >
                <SelectTrigger
                  className={cn(
                    'rounded-[14px] border-[#d1d5dc] bg-white',
                    missingClient && 'border-l-4 border-l-[#e7000b]',
                  )}
                >
                  <SelectValue placeholder={customersLoading ? 'Loading clients…' : 'Select client'} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {customerOptions.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.customer_name || c.customer_code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-[#4a5565]">Project</p>
              <div
                className={cn(
                  'rounded-[14px] border border-[#d1d5dc] bg-white px-3 py-2',
                  missingProject && 'border-l-4 border-l-[#e7000b]',
                )}
              >
                <TruncatedTextCell
                  text={projectLabel}
                  dialogTitle="Project title"
                  className="font-medium text-[#101828]"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Seller reference</Label>
              <Input
                value={meta.seller_reference}
                onChange={(e) => setMeta((m) => ({ ...m, seller_reference: e.target.value }))}
                className="rounded-[14px] border-[#d1d5dc]"
                placeholder="Our ref"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Customer reference</Label>
              <Input
                value={meta.customer_reference}
                onChange={(e) => setMeta((m) => ({ ...m, customer_reference: e.target.value }))}
                className="rounded-[14px] border-[#d1d5dc]"
                placeholder="Customer ref"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Client PIC name</Label>
              <Input
                value={meta.customer_pic_name}
                onChange={(e) => setMeta((m) => ({ ...m, customer_pic_name: e.target.value }))}
                className="rounded-[14px] border-[#d1d5dc]"
                placeholder="PIC name"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Client telephone</Label>
              <Input
                value={meta.customer_phone}
                onChange={(e) => setMeta((m) => ({ ...m, customer_phone: e.target.value }))}
                className="rounded-[14px] border-[#d1d5dc]"
                placeholder="Client phone"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Client email</Label>
              <Input
                type="email"
                value={meta.customer_email}
                onChange={(e) => setMeta((m) => ({ ...m, customer_email: e.target.value }))}
                className="rounded-[14px] border-[#d1d5dc]"
                placeholder="client@email.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Order date</Label>
              <Input
                type="date"
                value={meta.issued_on ? meta.issued_on.slice(0, 10) : ''}
                onChange={(e) => setMeta((m) => ({ ...m, issued_on: e.target.value ? `${e.target.value}T00:00:00` : '' }))}
                className={cn(
                  'max-w-full rounded-[14px] border-[#d1d5dc]',
                  missingOrderDate && 'border-l-4 border-l-[#e7000b]',
                )}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Payment term</Label>
              <Select
                value={meta.payment_term_code || '__none__'}
                onValueChange={(v) => setMeta((m) => ({ ...m, payment_term_code: v === '__none__' ? '' : v }))}
              >
                <SelectTrigger
                  className={cn(
                    'w-full max-w-full bg-white',
                    missingPayment && 'border-l-4 border-l-[#e7000b]',
                  )}
                >
                  <SelectValue placeholder="Select payment term" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {paymentTerms.map((pt) => (
                    <SelectItem key={pt.code} value={pt.code}>
                      {pt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Validity period (days)</Label>
              <Input
                inputMode="numeric"
                value={meta.quotation_validity_days}
                onChange={(e) => setMeta((m) => ({ ...m, quotation_validity_days: e.target.value }))}
                placeholder="e.g. 30"
                className={cn('rounded-[14px] border-[#d1d5dc]', missingValidity && 'border-l-4 border-l-[#e7000b]')}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Assigned salesperson</Label>
              <Select
                value={meta.salesperson_user_id || '__none__'}
                onValueChange={(v) => setMeta((m) => ({ ...m, salesperson_user_id: v === '__none__' ? '' : v }))}
              >
                <SelectTrigger
                  className={cn(
                    'w-full max-w-full bg-white',
                    missingSales && 'border-l-4 border-l-[#e7000b]',
                  )}
                >
                  <SelectValue placeholder="Select user" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {(u.name || '').trim() || u.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[#4a5565]">Quotation template</Label>
              <Select
                value={pkgSelectId || '__none__'}
                onValueChange={(v) => {
                  const next = v === '__none__' ? '' : v;
                  const cur = master?.quotation_package_template_id || '';
                  if (next === cur) return;
                  setPendingPkgId(next);
                  setConfirmPkgOpen(true);
                }}
                disabled={replacingPkg}
              >
                <SelectTrigger className="w-full max-w-full bg-white">
                  <SelectValue placeholder="Select template" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {packageTemplates.map((tpl) => (
                    <SelectItem key={tpl.id} value={tpl.id}>
                      {tpl.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-[#e5e7eb] bg-white shadow-sm">
          <Tabs value={editTab} onValueChange={(v) => setEditTab(v as 'orderLines' | 'internalNotes')} className="w-full">
            <div className="border-b border-[#e5e7eb] px-6 pt-4">
              <TabsList className="h-auto w-full justify-start gap-8 rounded-none border-0 bg-transparent p-0">
                <TabsTrigger
                  value="orderLines"
                  className="rounded-none border-b-2 border-transparent px-0 pb-3 text-base font-medium data-[state=active]:border-[#e7000b] data-[state=active]:text-[#e7000b]"
                >
                  Order lines
                </TabsTrigger>
                <TabsTrigger
                  value="internalNotes"
                  className="rounded-none border-b-2 border-transparent px-0 pb-3 text-base font-medium data-[state=active]:border-[#e7000b] data-[state=active]:text-[#e7000b]"
                >
                  Internal notes
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="internalNotes" className="p-6">
              <QuotationReactQuill
                value={meta.notes}
                onChange={(html) => setMeta((m) => ({ ...m, notes: html }))}
                placeholder="Internal notes…"
                minHeightPx={200}
              />
            </TabsContent>

            <TabsContent value="orderLines" className="space-y-6 p-6">
              <OrderLinesEditor
                lines={lines}
                moveLine={moveLine}
                updateLine={updateLine}
                removeLine={removeLine}
                addLine={addLine}
                onPickProduct={onPickProduct}
                fetchProductOptions={fetchProductOptions}
                uoms={uoms}
                taxRates={taxRates}
                quotedCurrency={master?.quoted_currency}
                showUnitCost={showEditUnitCost}
                onToggleUnitCost={() => setShowEditUnitCost((s) => !s)}
                productById={productById}
              />

              <div className="ms-auto flex w-full max-w-sm flex-col gap-2">
                <div className="flex justify-between text-sm">
                  <span className="text-[#4a5565]">Subtotal</span>
                  <span className="tabular-nums text-[#101828]">
                    {formatOrderLineMoney(orderLinesMoneyTotals.subtotal, master?.quoted_currency)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#4a5565]">Discount</span>
                  <span className="tabular-nums text-[#101828]">
                    {formatOrderLineMoney(orderLinesMoneyTotals.discountTotal, master?.quoted_currency)}
                  </span>
                </div>
                <div className="flex justify-between border-t border-[#e5e7eb] pt-2 text-base">
                  <span className="text-[#101828]">Total</span>
                  <span className="tabular-nums font-normal text-[#101828]">
                    {formatOrderLineMoney(orderLinesMoneyTotals.subtotal, master?.quoted_currency)}
                  </span>
                </div>
                <div className="flex justify-between pt-1 text-sm">
                  <span className="text-[#4a5565]">Margin</span>
                  <span className="tabular-nums font-medium text-[#008236]">
                    {editHasCostData ? formatOrderLineMoney(editMarginAmt, master?.quoted_currency) : '—'}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#4a5565]">Margin %</span>
                  <span className="tabular-nums font-medium text-[#008236]">
                    {editHasCostData ? `${editMarginPct.toFixed(2)}%` : '—'}
                  </span>
                </div>
              </div>

              <div className="border-t border-[#e5e7eb] pt-6">
                <h3 className="mb-3 text-sm font-medium text-[#0a0a0a]">Terms &amp; conditions</h3>
                <QuotationReactQuill
                  value={meta.terms_html}
                  onChange={(html) => setMeta((m) => ({ ...m, terms_html: html }))}
                  placeholder="Terms & conditions…"
                  minHeightPx={160}
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <AlertDialog open={confirmPkgOpen} onOpenChange={setConfirmPkgOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Replace quotation content?</AlertDialogTitle>
              <AlertDialogDescription>
                Applying a different quotation template will overwrite order lines and quotation details with the template
                defaults. This cannot be undone from here. Continue?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel
                onClick={() => {
                  setPendingPkgId(null);
                }}
              >
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                className="bg-[#e7000b] hover:bg-[#e7000b]/90"
                disabled={replacingPkg}
                onClick={(e) => {
                  e.preventDefault();
                  void confirmPkgApply();
                }}
              >
                {replacingPkg ? <Loader2 className="size-4 animate-spin" /> : 'Yes, apply template'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
      {master?.id ? (
        <EntityActivitiesDock variant="master_quotation" entityId={master.id} canPost={canEditMaster} />
      ) : null}
    </Container>
  );
}
