'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Edit, Trash2, Plus, ExternalLink, Search, X, Layers, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  usePromotion,
  useDeletePromotion,
  useAddPromotionProduct,
  useRemovePromotionProduct,
  useUpdatePromotionProductPrice,
  usePromotions,
  useCreatePromotionGroup,
  useUpdatePromotionGroup,
  useDeletePromotionGroup,
} from '../hooks/usePromotions';
import { useProducts } from '../../../master-data-management/products/hooks/useProducts';
import type { GetProductsParams } from '../../../master-data-management/products/services/productService';
import { formatPromotionBoundaryInMalaysia } from '@/lib/helpers';
import { toast } from 'sonner';
import { LoaderCircleIcon } from 'lucide-react';
import PromotionAttachmentsTab from './PromotionAttachmentsTab';
import RecordNavigation from '@/components/common/RecordNavigation';
import type { PromotionProduct, PromotionGroup } from '../types/promotion.types';

type FocTierRow = { purchase: string; foc: string };

const emptyFocTierRow = (): FocTierRow => ({ purchase: '', foc: '' });

function focTiersToRows(g: PromotionGroup): FocTierRow[] {
  if (g.foc_tiers?.length) {
    return g.foc_tiers.map((t) => ({
      purchase: String(t.purchase_quantity),
      foc: String(t.foc_quantity),
    }));
  }
  return [emptyFocTierRow()];
}

function formatFocTiersLabel(group: PromotionGroup): string | null {
  const tiers = group.foc_tiers ?? [];
  if (!tiers.length) return null;
  return tiers.map((t) => `Buy ${t.purchase_quantity} get ${t.foc_quantity} free`).join(' · ');
}

/** User enters 0–100 (% off list); API stores fraction 0–1. */
function parseDealerDiscountPercentInput(raw: string): { ok: true; fraction: number | null } | { ok: false } {
  const t = raw.trim();
  if (t === '') return { ok: true, fraction: null };
  const n = Number.parseFloat(t.replace(',', '.'));
  if (Number.isNaN(n) || n < 0 || n > 100) return { ok: false };
  return { ok: true, fraction: n / 100 };
}

function fractionToPercentInputString(fraction: number | null | undefined): string {
  if (fraction == null || Number.isNaN(Number(fraction))) return '';
  const pct = Number(fraction) * 100;
  const rounded = Math.round(pct * 10000) / 10000;
  return String(rounded);
}

interface PromotionDetailProps {
  promotionId: string;
}

export default function PromotionDetail({ promotionId }: PromotionDetailProps) {
  const router = useRouter();
  const { data: promotion, isLoading } = usePromotion(promotionId);
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = usePromotions(navigationParams);
  const navigationItems = navigationData?.data ?? [];
  const deleteMutation = useDeletePromotion();
  const addProductMutation = useAddPromotionProduct();
  const removeProductMutation = useRemovePromotionProduct();
  const updatePriceMutation = useUpdatePromotionProductPrice();
  const createGroupMutation = useCreatePromotionGroup();
  const updateGroupMutation = useUpdatePromotionGroup();
  const deleteGroupMutation = useDeletePromotionGroup();

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [addProductDialogOpen, setAddProductDialogOpen] = useState(false);
  const [addProductGroupId, setAddProductGroupId] = useState<string>('');
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [groupEditTarget, setGroupEditTarget] = useState<PromotionGroup | null>(null);
  const [groupFormName, setGroupFormName] = useState('');
  const [groupFormSort, setGroupFormSort] = useState('');
  const [focTierRows, setFocTierRows] = useState<FocTierRow[]>([emptyFocTierRow()]);
  const [editProductDialogOpen, setEditProductDialogOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState<string>('');
  const [promotionPrice, setPromotionPrice] = useState<string>('');
  const [editingProduct, setEditingProduct] = useState<{
    id: string;
    product_id: string;
    promotion_price: number | null;
    dealer_discount_percent: number | null;
    list_price: number | null;
  } | null>(null);
  const [dealerDiscountInput, setDealerDiscountInput] = useState('');
  const [listPriceInput, setListPriceInput] = useState('');
  const [addProductDealerDiscount, setAddProductDealerDiscount] = useState('');
  const [productCodeSearch, setProductCodeSearch] = useState('');

  // Fetch all products for the add product dialog
  const productsParams: GetProductsParams = {
    pageIndex: 0,
    pageSize: 1000,
    sorting: [],
    searchQuery: '',
    status: 'all',
  };
  const { data: productsData } = useProducts(productsParams);
  const allProducts = productsData?.data || [];
  const sortedGroupsBase = useMemo(() => {
    const groups = [...(promotion?.promotion_groups ?? [])];
    groups.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    return groups;
  }, [promotion?.promotion_groups]);

  const defaultGroupId = useMemo(() => {
    const g = promotion?.promotion_groups?.find((x) => x.group_name === 'Default');
    return g?.id;
  }, [promotion?.promotion_groups]);

  const productIdsInAddTargetGroup = useMemo(() => {
    if (!promotion?.products?.length || !addProductGroupId) return new Set<string>();
    return new Set(
      promotion.products.filter((p) => p.promotion_group_id === addProductGroupId).map((p) => p.product_id),
    );
  }, [promotion?.products, addProductGroupId]);

  const availableProducts = allProducts.filter((p) => !productIdsInAddTargetGroup.has(p.id));

  const filteredPromotionProducts = useMemo(() => {
    const list = promotion?.products ?? [];
    const q = productCodeSearch.trim().toLowerCase();
    if (!q) return list;
    return list.filter((pp) => (pp.product?.product_code || '').toLowerCase().includes(q));
  }, [promotion?.products, productCodeSearch]);

  const filteredPromotionGroups = useMemo(() => {
    const q = productCodeSearch.trim().toLowerCase();
    if (!sortedGroupsBase.length) return [];
    return sortedGroupsBase.map((g) => ({
      ...g,
      promotion_products: (g.promotion_products ?? []).filter((pp) =>
        !q || (pp.product?.product_code || '').toLowerCase().includes(q),
      ),
    }));
  }, [sortedGroupsBase, productCodeSearch]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!promotion) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Promotion not found</p>
        <Button variant="outline" onClick={() => router.push('/marketing-management/promotions')} className="mt-4">
          Back to Promotions
        </Button>
      </div>
    );
  }

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(promotionId);
      router.push('/marketing-management/promotions');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const handleAddProduct = async () => {
    if (!addProductGroupId) {
      toast.error('Select a promotion group');
      return;
    }
    if (!selectedProductId) {
      toast.error('Please select a product');
      return;
    }

    const price = promotionPrice ? parseFloat(promotionPrice) : undefined;

    const ddRaw = addProductDealerDiscount;
    const ddParsed = parseDealerDiscountPercentInput(ddRaw);
    if (!ddParsed.ok) {
      toast.error('Dealer discount must be a percentage between 0 and 100.');
      return;
    }
    const dealerDiscountPercent =
      ddRaw.trim() === '' ? undefined : ddParsed.fraction;

    try {
      await addProductMutation.mutateAsync({
        promotionId,
        productId: selectedProductId,
        promotionPrice: price,
        promotionGroupId: addProductGroupId || undefined,
        dealerDiscountPercent,
      });
      setAddProductDialogOpen(false);
      setSelectedProductId('');
      setPromotionPrice('');
      setAddProductGroupId('');
      setAddProductDealerDiscount('');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const handleEditProduct = (product: {
    id: string;
    product_id: string;
    promotion_price: number | null;
    dealer_discount_percent: number | null;
    list_price: number | null;
  }) => {
    setEditingProduct(product);
    setPromotionPrice(product.promotion_price?.toString() || '');
    setDealerDiscountInput(fractionToPercentInputString(product.dealer_discount_percent));
    setListPriceInput(
      product.list_price != null && !Number.isNaN(Number(product.list_price))
        ? String(Number(product.list_price))
        : '',
    );
    setEditProductDialogOpen(true);
  };

  const handleUpdateProductPrice = async () => {
    if (!editingProduct) return;

    const price = promotionPrice ? parseFloat(promotionPrice) : 0;
    const ddParsed = parseDealerDiscountPercentInput(dealerDiscountInput);
    if (!ddParsed.ok) {
      toast.error('Dealer discount must be a percentage between 0 and 100.');
      return;
    }
    const listPrice = Number.parseFloat(listPriceInput.replace(',', '.'));
    if (Number.isNaN(listPrice) || listPrice < 0) {
      toast.error('Enter a valid list price (0 or greater).');
      return;
    }

    try {
      await updatePriceMutation.mutateAsync({
        promotionId,
        lineId: editingProduct.id,
        promotionPrice: price,
        dealerDiscountPercent: ddParsed.fraction,
        listPrice,
      });
      setEditProductDialogOpen(false);
      setEditingProduct(null);
      setPromotionPrice('');
      setDealerDiscountInput('');
      setListPriceInput('');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const handleRemoveProduct = async (lineId: string) => {
    if (!confirm('Are you sure you want to remove this product line from the promotion?')) {
      return;
    }

    try {
      await removeProductMutation.mutateAsync({
        promotionId,
        lineId,
      });
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const openCreateGroupDialog = () => {
    setGroupEditTarget(null);
    setGroupFormName('');
    setGroupFormSort('');
    setFocTierRows([emptyFocTierRow()]);
    setGroupDialogOpen(true);
  };

  const openEditGroupDialog = (g: PromotionGroup) => {
    setGroupEditTarget(g);
    setGroupFormName(g.group_name);
    setGroupFormSort(g.sort_order != null ? String(g.sort_order) : '');
    setFocTierRows(focTiersToRows(g));
    setGroupDialogOpen(true);
  };

  const handleSaveGroup = async () => {
    const name = groupFormName.trim();
    if (!name) {
      toast.error('Group name is required');
      return;
    }
    let sortOrder: number | undefined;
    if (groupFormSort.trim() !== '') {
      sortOrder = parseInt(groupFormSort, 10);
      if (Number.isNaN(sortOrder)) {
        toast.error('Invalid sort order');
        return;
      }
    }

    const focTiers: { purchase_quantity: number; foc_quantity: number }[] = [];
    for (const row of focTierRows) {
      const p = row.purchase.trim();
      const f = row.foc.trim();
      if (p === '' && f === '') continue;
      if (p === '' || f === '') {
        toast.error('Complete both purchase qty and FOC qty for each row, or clear the row.');
        return;
      }
      const pq = parseInt(p, 10);
      const fq = parseInt(f, 10);
      if (Number.isNaN(pq) || pq < 1) {
        toast.error('Purchase quantity must be at least 1.');
        return;
      }
      if (Number.isNaN(fq) || fq < 0) {
        toast.error('FOC quantity must be 0 or more.');
        return;
      }
      focTiers.push({ purchase_quantity: pq, foc_quantity: fq });
    }

    try {
      if (groupEditTarget) {
        await updateGroupMutation.mutateAsync({
          promotionId,
          groupId: groupEditTarget.id,
          data: {
            group_name: name,
            ...(sortOrder !== undefined ? { sort_order: sortOrder } : {}),
            foc_tiers: focTiers,
          },
        });
      } else {
        await createGroupMutation.mutateAsync({
          promotionId,
          data: {
            group_name: name,
            ...(sortOrder !== undefined ? { sort_order: sortOrder } : {}),
            ...(focTiers.length ? { foc_tiers: focTiers } : {}),
          },
        });
      }
      setGroupDialogOpen(false);
      setGroupEditTarget(null);
      setGroupFormName('');
      setGroupFormSort('');
      setFocTierRows([emptyFocTierRow()]);
    } catch {
      /* toast in hook */
    }
  };

  const handleDeleteGroupClick = (g: PromotionGroup) => {
    const full = sortedGroupsBase.find((x) => x.id === g.id);
    const n = full?.promotion_products?.length ?? 0;
    const msg =
      n > 0
        ? `Delete group "${g.group_name}"? This will remove ${n} product line(s) in this group. This cannot be undone.`
        : `Delete group "${g.group_name}"? This cannot be undone.`;
    if (!confirm(msg)) return;
    deleteGroupMutation.mutate({ promotionId, groupId: g.id });
  };

  const openAddProductForGroup = (groupId: string) => {
    setAddProductGroupId(groupId);
    setSelectedProductId('');
    setPromotionPrice('');
    setAddProductDealerDiscount('');
    setAddProductDialogOpen(true);
  };

  const typeLabels: Record<string, string> = {
    price_override: 'Price Override',
    discount_percent: 'Discount %',
    discount_amount: 'Discount Amount',
    bundle: 'Bundle',
    other: 'Other',
  };

  const fmtMoney = (n: number) =>
    new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(n);

  const renderProductRow = (pp: PromotionProduct) => {
    const listPrice = Number(pp.product?.list_price) || 0;
    const promoPrice = Number(pp.promotion_price) || listPrice;
    const discount = listPrice - promoPrice;
    const discountPercent = listPrice > 0 ? (discount / listPrice) * 100 : 0;
    const dd = pp.dealer_discount_percent != null ? Number(pp.dealer_discount_percent) : null;
    const dealerCost = pp.dealer_cost != null ? Number(pp.dealer_cost) : null;
    const margin = pp.list_to_dealer_margin_amount != null ? Number(pp.list_to_dealer_margin_amount) : null;

    const productHref = pp.product_id ? `/master-data-management/products/${pp.product_id}` : null;

    return (
      <tr key={pp.id} className="border-b">
        <td className="p-2 text-sm">
          {productHref ? (
            <Link href={productHref} className="text-primary hover:underline font-medium">
              {pp.product?.product_code || '-'}
            </Link>
          ) : (
            pp.product?.product_code || '-'
          )}
        </td>
        <td className="p-2 text-sm">
          {productHref ? (
            <Link href={productHref} className="text-primary hover:underline">
              {pp.product?.product_name || '-'}
            </Link>
          ) : (
            pp.product?.product_name || '-'
          )}
        </td>
        <td className="p-2 text-sm text-right">{fmtMoney(listPrice)}</td>
        <td className="p-2 text-sm text-right">{fmtMoney(promoPrice)}</td>
        <td className="p-2 text-sm text-right">
          {discount > 0 ? <Badge variant="success">{fmtMoney(discount)}</Badge> : '-'}
        </td>
        <td className="p-2 text-sm text-right">
          {discountPercent > 0 ? <Badge variant="info">{discountPercent.toFixed(1)}%</Badge> : '-'}
        </td>
        <td className="p-2 text-sm text-right">
          {dd != null && !Number.isNaN(dd) ? <span className="text-muted-foreground">{(dd * 100).toFixed(0)}%</span> : '-'}
        </td>
        <td className="p-2 text-sm text-right">{dealerCost != null ? fmtMoney(dealerCost) : '-'}</td>
        <td className="p-2 text-right">
          <div className="flex justify-end gap-2">
            {productHref && (
              <Button type="button" variant="ghost" size="sm" title="View product" onClick={() => router.push(productHref)}>
                <ExternalLink className="size-4" />
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() =>
                handleEditProduct({
                  id: pp.id,
                  product_id: pp.product_id,
                  promotion_price: pp.promotion_price ?? null,
                  dealer_discount_percent: pp.dealer_discount_percent ?? null,
                  list_price:
                    pp.product?.list_price != null ? Number(pp.product.list_price) : null,
                })
              }
            >
              <Edit className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => handleRemoveProduct(pp.id)}
              disabled={removeProductMutation.isPending}
            >
              {removeProductMutation.isPending ? (
                <LoaderCircleIcon className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4 text-destructive" />
              )}
            </Button>
          </div>
        </td>
      </tr>
    );
  };

  const tableHead = (
    <thead>
      <tr className="border-b">
        <th className="text-left p-2 font-medium text-sm">Product Code</th>
        <th className="text-left p-2 font-medium text-sm">Product Name</th>
        <th className="text-right p-2 font-medium text-sm">List Price</th>
        <th className="text-right p-2 font-medium text-sm">Promo Price</th>
        <th className="text-right p-2 font-medium text-sm">Discount</th>
        <th className="text-right p-2 font-medium text-sm">Discount %</th>
        <th className="text-right p-2 font-medium text-sm">Dealer Discount %</th>
        <th className="text-right p-2 font-medium text-sm">Dealer cost</th>
        <th className="text-right p-2 font-medium text-sm">Actions</th>
      </tr>
    </thead>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{promotion.name}</h1>
            <Badge variant={promotion.is_active ? 'success' : 'secondary'} appearance="ghost">
              <BadgeDot />
              {promotion.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Promo Code: {promotion.promo_code} • Type: {typeLabels[promotion.promo_type] || promotion.promo_type}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={promotionId}
            items={navigationItems}
            basePath="/marketing-management/promotions"
          />
          <Button variant="outline" onClick={() => router.push(`/marketing-management/promotions/${promotionId}/edit`)}>
            <Edit className="size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Promotion Information */}
      <Card>
        <CardHeader>
          <CardTitle>Promotion Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Start Date</p>
              <p className="font-medium">{formatPromotionBoundaryInMalaysia(promotion.start_date)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">End Date</p>
              <p className="font-medium">{formatPromotionBoundaryInMalaysia(promotion.end_date)}</p>
            </div>
            {promotion.access_levels && promotion.access_levels.length > 0 && (
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Access type</p>
                <p className="font-medium">
                  {promotion.access_levels
                    .map((l) => l.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()))
                    .join(', ')}
                </p>
              </div>
            )}
            {promotion.description && (
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Description</p>
                <p className="font-medium">{promotion.description}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Attachments Section */}
      <PromotionAttachmentsTab promotionId={promotionId} isEditMode={false} promotionAccessLevels={promotion.access_levels ?? undefined} />

      {/* Products Section */}
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div className="space-y-1 min-w-0">
            <CardTitle>Products in Promotion</CardTitle>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <Button variant="outline" onClick={openCreateGroupDialog} className="shrink-0">
              <Layers className="size-4" />
              Add group
            </Button>
            <Button
              onClick={() => {
                const first = defaultGroupId || sortedGroupsBase[0]?.id || '';
                setAddProductGroupId(first);
                setSelectedProductId('');
                setPromotionPrice('');
                setAddProductDealerDiscount('');
                setAddProductDialogOpen(true);
              }}
              className="shrink-0"
              disabled={sortedGroupsBase.length === 0}
              title={sortedGroupsBase.length === 0 ? 'Create a promotion group first' : undefined}
            >
              <Plus className="size-4" />
              Add product
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {promotion.products && promotion.products.length > 0 ? (
            <div className="space-y-4">
              <div className="relative max-w-sm">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search by product code..."
                  value={productCodeSearch}
                  onChange={(e) => setProductCodeSearch(e.target.value)}
                  className="ps-9"
                  aria-label="Filter products by product code"
                />
                {productCodeSearch ? (
                  <Button
                    type="button"
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setProductCodeSearch('')}
                  >
                    <X className="size-4" />
                  </Button>
                ) : null}
              </div>
              {filteredPromotionGroups.length > 0 ? (
                <div className="space-y-8">
                  {filteredPromotionGroups.map((group) => {
                    const focTiersLabel = formatFocTiersLabel(group);
                    return (
                    <Collapsible key={group.id} defaultOpen>
                      <div className="space-y-0 rounded-lg border bg-card/50">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
                          <CollapsibleTrigger asChild>
                            <button
                              type="button"
                              className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&[data-state=closed]_svg]:-rotate-90"
                              aria-label={`${group.group_name}: expand or collapse`}
                            >
                              <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform duration-200" />
                              <div className="flex min-w-0 flex-wrap items-baseline gap-2">
                                <h3 className="font-semibold text-base">{group.group_name}</h3>
                                {focTiersLabel ? (
                                  <span className="text-sm text-muted-foreground">{focTiersLabel}</span>
                                ) : null}
                                <span className="text-xs text-muted-foreground tabular-nums">
                                  ({group.promotion_products.length} line
                                  {group.promotion_products.length === 1 ? '' : 's'})
                                </span>
                              </div>
                            </button>
                          </CollapsibleTrigger>
                          <div className="flex flex-wrap items-center gap-2 shrink-0">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8"
                              onClick={() => openAddProductForGroup(group.id)}
                            >
                              <Plus className="size-4" />
                              Add product
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              title="Edit group"
                              onClick={() => openEditGroupDialog(group)}
                            >
                              <Edit className="size-4" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              title="Delete group"
                              onClick={() => handleDeleteGroupClick(group)}
                              disabled={deleteGroupMutation.isPending}
                            >
                              <Trash2 className="size-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                        <CollapsibleContent>
                          <div className="px-3 pb-3 pt-1">
                            {group.promotion_products.length === 0 ? (
                              <p className="text-sm text-muted-foreground">
                                {productCodeSearch.trim()
                                  ? `No products match "${productCodeSearch.trim()}" in this group.`
                                  : 'No products in this group yet. Use Add product above to add SKUs.'}
                              </p>
                            ) : (
                              <div className="overflow-x-auto">
                                <table className="w-full min-w-[960px]">
                                  {tableHead}
                                  <tbody>{group.promotion_products.map((pp) => renderProductRow(pp))}</tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        </CollapsibleContent>
                      </div>
                    </Collapsible>
                    );
                  })}
                </div>
              ) : filteredPromotionProducts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No products match &quot;{productCodeSearch.trim()}&quot;. Clear the search to see all products.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[960px]">
                    {tableHead}
                    <tbody>{filteredPromotionProducts.map((pp) => renderProductRow(pp))}</tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No products in this promotion yet.</p>
          )}
        </CardContent>
      </Card>

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Delete</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the promotion{' '}
              <strong className="text-foreground">{promotion.name}</strong> (
              {promotion.promo_code})? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Product Dialog */}
      <Dialog
        open={addProductDialogOpen}
        onOpenChange={(open) => {
          setAddProductDialogOpen(open);
          if (!open) {
            setSelectedProductId('');
            setPromotionPrice('');
            setAddProductGroupId('');
            setAddProductDealerDiscount('');
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add product to promotion</DialogTitle>
            <DialogDescription>
              The same SKU can appear in multiple groups as separate lines.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Promotion group *</Label>
              <Select value={addProductGroupId} onValueChange={setAddProductGroupId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select group" />
                </SelectTrigger>
                <SelectContent>
                  {sortedGroupsBase.map((g) => (
                    <SelectItem key={g.id} value={g.id}>
                      {g.group_name}
                    </SelectItem>
                  ))}
                  {sortedGroupsBase.length === 0 && (
                    <SelectItem value="__no_groups__" disabled>
                      No groups — use Add group first
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Product *</Label>
              <Select value={selectedProductId} onValueChange={setSelectedProductId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a product" />
                </SelectTrigger>
                <SelectContent>
                  {availableProducts.map((product) => (
                    <SelectItem key={product.id} value={product.id}>
                      {product.product_code} - {product.product_name}
                    </SelectItem>
                  ))}
                  {availableProducts.length === 0 && (
                    <SelectItem value="__no_products__" disabled>
                      No available products for this group
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Promotion price (optional)</Label>
              <Input
                type="number"
                step="0.01"
                placeholder="Leave empty to use list price"
                value={promotionPrice}
                onChange={(e) => setPromotionPrice(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Dealer discount (% off list)</Label>
              <Input
                type="number"
                step="0.1"
                min={0}
                max={100}
                placeholder="e.g. 37"
                value={addProductDealerDiscount}
                onChange={(e) => setAddProductDealerDiscount(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Leave empty if not applicable.</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddProductDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAddProduct}
              disabled={!addProductGroupId || !selectedProductId || addProductMutation.isPending}
            >
              {addProductMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Adding...
                </>
              ) : (
                'Add product'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add / Edit promotion group */}
      <Dialog
        open={groupDialogOpen}
        onOpenChange={(open) => {
          setGroupDialogOpen(open);
          if (!open) {
            setGroupEditTarget(null);
            setGroupFormName('');
            setGroupFormSort('');
            setFocTierRows([emptyFocTierRow()]);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{groupEditTarget ? 'Edit promotion group' : 'New promotion group'}</DialogTitle>
            <DialogDescription>
              Set a name and optional FOC rule(s). Add multiple rows for different buy / free combinations (e.g.
              buy 10 get 1, buy 25 get 5). Leave all rows empty if no FOC rule applies.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Group name *</Label>
              <Input value={groupFormName} onChange={(e) => setGroupFormName(e.target.value)} placeholder="e.g. 10 FOC 1" />
            </div>
            <div className="space-y-2">
              <Label>Sort order</Label>
              <Input
                type="number"
                step="1"
                placeholder="Auto if empty"
                value={groupFormSort}
                onChange={(e) => setGroupFormSort(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Lower numbers appear first.</p>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label>FOC tiers (buy / free)</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={() => setFocTierRows((rows) => [...rows, emptyFocTierRow()])}
                >
                  <Plus className="size-4" />
                  Add tier
                </Button>
              </div>
              <div className="space-y-3">
                {focTierRows.map((row, idx) => (
                  <div key={idx} className="border rounded-md p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-muted-foreground">Tier {idx + 1}</span>
                      {focTierRows.length > 1 ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 text-destructive"
                          onClick={() => setFocTierRows((rows) => rows.filter((_, i) => i !== idx))}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-0.5">
                        <Label className="text-xs">Purchase qty</Label>
                        <Input
                          type="number"
                          step="1"
                          min="1"
                          placeholder="e.g. 10"
                          value={row.purchase}
                          onChange={(e) => {
                            const v = e.target.value;
                            setFocTierRows((rows) =>
                              rows.map((r, i) => (i === idx ? { ...r, purchase: v } : r)),
                            );
                          }}
                        />
                      </div>
                      <div className="space-y-0.5">
                        <Label className="text-xs">FOC qty</Label>
                        <Input
                          type="number"
                          step="1"
                          min="0"
                          placeholder="e.g. 1"
                          value={row.foc}
                          onChange={(e) => {
                            const v = e.target.value;
                            setFocTierRows((rows) =>
                              rows.map((r, i) => (i === idx ? { ...r, foc: v } : r)),
                            );
                          }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                When editing, saving with no tiers clears all FOC rules for this group.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGroupDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => void handleSaveGroup()}
              disabled={
                createGroupMutation.isPending || updateGroupMutation.isPending || !groupFormName.trim()
              }
            >
              {createGroupMutation.isPending || updateGroupMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Product Price Dialog */}
      <Dialog
        open={editProductDialogOpen}
        onOpenChange={(open) => {
          setEditProductDialogOpen(open);
          if (!open) {
            setEditingProduct(null);
            setPromotionPrice('');
            setDealerDiscountInput('');
            setListPriceInput('');
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit promotion line</DialogTitle>
            <DialogDescription>Edit pricing for this line.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {editingProduct && (
              <>
                <div className="space-y-2">
                  <Label>List price *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    min={0}
                    placeholder="List price"
                    value={listPriceInput}
                    onChange={(e) => setListPriceInput(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Promotion price (selling) *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="Enter promotion price"
                    value={promotionPrice}
                    onChange={(e) => setPromotionPrice(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Dealer discount (% off list)</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0}
                    max={100}
                    placeholder="e.g. 37"
                    value={dealerDiscountInput}
                    onChange={(e) => setDealerDiscountInput(e.target.value)}
                  />
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setEditProductDialogOpen(false);
              setEditingProduct(null);
              setPromotionPrice('');
              setDealerDiscountInput('');
              setListPriceInput('');
            }}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdateProductPrice}
              disabled={
                !promotionPrice.trim() ||
                !listPriceInput.trim() ||
                updatePriceMutation.isPending
              }
            >
              {updatePriceMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Updating...
                </>
              ) : (
                'Save'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
