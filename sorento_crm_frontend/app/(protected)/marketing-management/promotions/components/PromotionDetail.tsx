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
import { formatDate } from '@/lib/helpers';
import { toast } from 'sonner';
import { LoaderCircleIcon } from 'lucide-react';
import PromotionAttachmentsTab from './PromotionAttachmentsTab';
import RecordNavigation from '@/components/common/RecordNavigation';
import type { PromotionProduct, PromotionGroup } from '../types/promotion.types';

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
  const [groupFormPurchase, setGroupFormPurchase] = useState('');
  const [groupFormFoc, setGroupFormFoc] = useState('');
  const [editProductDialogOpen, setEditProductDialogOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState<string>('');
  const [promotionPrice, setPromotionPrice] = useState<string>('');
  const [editingProduct, setEditingProduct] = useState<{
    id: string;
    product_id: string;
    promotion_price: number | null;
    dealer_discount_percent: number | null;
  } | null>(null);
  const [dealerDiscountInput, setDealerDiscountInput] = useState('');
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

    const ddRaw = addProductDealerDiscount.trim();
    let dealerDiscountPercent: number | null | undefined;
    if (ddRaw === '') {
      dealerDiscountPercent = undefined;
    } else {
      const parsed = parseFloat(ddRaw);
      if (Number.isNaN(parsed)) {
        toast.error('Invalid dealer discount (use decimal like 0.37 for 37% off list)');
        return;
      }
      dealerDiscountPercent = parsed;
    }

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
  }) => {
    setEditingProduct(product);
    setPromotionPrice(product.promotion_price?.toString() || '');
    setDealerDiscountInput(
      product.dealer_discount_percent != null ? String(product.dealer_discount_percent) : '',
    );
    setEditProductDialogOpen(true);
  };

  const handleUpdateProductPrice = async () => {
    if (!editingProduct) return;

    const price = promotionPrice ? parseFloat(promotionPrice) : 0;
    const ddRaw = dealerDiscountInput.trim();
    const dealerDiscountPercent = ddRaw === '' ? null : parseFloat(ddRaw);
    if (ddRaw !== '' && Number.isNaN(dealerDiscountPercent!)) {
      toast.error('Invalid dealer discount (use decimal like 0.37 for 37% off list)');
      return;
    }

    try {
      await updatePriceMutation.mutateAsync({
        promotionId,
        lineId: editingProduct.id,
        promotionPrice: price,
        dealerDiscountPercent,
      });
      setEditProductDialogOpen(false);
      setEditingProduct(null);
      setPromotionPrice('');
      setDealerDiscountInput('');
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
    setGroupFormPurchase('');
    setGroupFormFoc('');
    setGroupDialogOpen(true);
  };

  const openEditGroupDialog = (g: PromotionGroup) => {
    setGroupEditTarget(g);
    setGroupFormName(g.group_name);
    setGroupFormSort(g.sort_order != null ? String(g.sort_order) : '');
    setGroupFormPurchase(
      g.purchase_quantity_for_foc != null ? String(g.purchase_quantity_for_foc) : '',
    );
    setGroupFormFoc(g.foc_quantity != null ? String(g.foc_quantity) : '');
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
    let pq: number | null | undefined;
    if (groupFormPurchase.trim() === '') {
      pq = groupEditTarget ? null : undefined;
    } else {
      const v = parseInt(groupFormPurchase, 10);
      if (Number.isNaN(v)) {
        toast.error('Invalid purchase quantity (FOC)');
        return;
      }
      pq = v;
    }
    let fq: number | null | undefined;
    if (groupFormFoc.trim() === '') {
      fq = groupEditTarget ? null : undefined;
    } else {
      const v = parseInt(groupFormFoc, 10);
      if (Number.isNaN(v)) {
        toast.error('Invalid FOC quantity');
        return;
      }
      fq = v;
    }

    try {
      if (groupEditTarget) {
        await updateGroupMutation.mutateAsync({
          promotionId,
          groupId: groupEditTarget.id,
          data: {
            group_name: name,
            ...(sortOrder !== undefined ? { sort_order: sortOrder } : {}),
            purchase_quantity_for_foc: pq ?? null,
            foc_quantity: fq ?? null,
          },
        });
      } else {
        await createGroupMutation.mutateAsync({
          promotionId,
          data: {
            group_name: name,
            ...(sortOrder !== undefined ? { sort_order: sortOrder } : {}),
            ...(pq !== undefined && pq !== null ? { purchase_quantity_for_foc: pq } : {}),
            ...(fq !== undefined && fq !== null ? { foc_quantity: fq } : {}),
          },
        });
      }
      setGroupDialogOpen(false);
      setGroupEditTarget(null);
      setGroupFormName('');
      setGroupFormSort('');
      setGroupFormPurchase('');
      setGroupFormFoc('');
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
        <td className="p-2 text-sm text-right">{margin != null ? fmtMoney(margin) : '-'}</td>
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
              <p className="font-medium">{formatDate(new Date(promotion.start_date))}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">End Date</p>
              <p className="font-medium">{formatDate(new Date(promotion.end_date))}</p>
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
            <p className="text-sm text-muted-foreground">
              Organise lines into bundle / FOC groups. Each group can have its own buy-N-get-M rule.
            </p>
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
                  {filteredPromotionGroups.map((group) => (
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
                                {group.purchase_quantity_for_foc != null && group.foc_quantity != null ? (
                                  <span className="text-sm text-muted-foreground">
                                    Buy {group.purchase_quantity_for_foc} get {group.foc_quantity} free (FOC)
                                  </span>
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
                  ))}
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
              Choose the group and product. Optional dealer discount is fraction off list (e.g. 0.37). The same SKU
              can appear in multiple groups as separate lines.
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
              <Label>Dealer discount (off list)</Label>
              <Input
                type="number"
                step="0.01"
                placeholder="e.g. 0.37 for 37% off list → dealer cost"
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
            setGroupFormPurchase('');
            setGroupFormFoc('');
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{groupEditTarget ? 'Edit promotion group' : 'New promotion group'}</DialogTitle>
            <DialogDescription>
              Set a name and optional FOC rule (buy N paid units, get M free). Leave FOC fields empty if not
              applicable.
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
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Purchase qty (FOC)</Label>
                <Input
                  type="number"
                  step="1"
                  min="0"
                  placeholder="e.g. 10"
                  value={groupFormPurchase}
                  onChange={(e) => setGroupFormPurchase(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>FOC qty</Label>
                <Input
                  type="number"
                  step="1"
                  min="0"
                  placeholder="e.g. 1"
                  value={groupFormFoc}
                  onChange={(e) => setGroupFormFoc(e.target.value)}
                />
              </div>
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
      <Dialog open={editProductDialogOpen} onOpenChange={setEditProductDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit promotion line</DialogTitle>
            <DialogDescription>
              Update promo selling price and optional dealer discount (fraction off list, e.g. 0.37).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {editingProduct && (
              <>
                <div className="space-y-2">
                  <Label>Promotion price (selling) *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="Enter promotion price"
                    value={promotionPrice}
                    onChange={(e) => setPromotionPrice(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    List price:{' '}
                    {new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(
                      Number(
                        promotion.products?.find((p) => p.id === editingProduct.id)?.product?.list_price,
                      ) || 0,
                    )}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Dealer discount (off list)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="e.g. 0.37 for 37% off list → dealer cost"
                    value={dealerDiscountInput}
                    onChange={(e) => setDealerDiscountInput(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Leave empty to clear dealer cost / margin.</p>
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
            }}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdateProductPrice}
              disabled={!promotionPrice || updatePriceMutation.isPending}
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
