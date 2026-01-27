'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Plus } from 'lucide-react';
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
import { usePromotion, useDeletePromotion, useAddPromotionProduct, useRemovePromotionProduct, useUpdatePromotionProductPrice, usePromotions } from '../hooks/usePromotions';
import { useProducts } from '../../../master-data-management/products/hooks/useProducts';
import type { GetProductsParams } from '../../../master-data-management/products/services/productService';
import { formatDate } from '@/lib/helpers';
import { toast } from 'sonner';
import { LoaderCircleIcon } from 'lucide-react';
import PromotionAttachmentsTab from './PromotionAttachmentsTab';
import RecordNavigation from '@/components/common/RecordNavigation';

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
  
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [addProductDialogOpen, setAddProductDialogOpen] = useState(false);
  const [editProductDialogOpen, setEditProductDialogOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState<string>('');
  const [promotionPrice, setPromotionPrice] = useState<string>('');
  const [editingProduct, setEditingProduct] = useState<{ id: string; product_id: string; promotion_price: number | null } | null>(null);

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
  const existingProductIds = promotion?.products?.map(p => p.product_id) || [];
  const availableProducts = allProducts.filter(p => !existingProductIds.includes(p.id));

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
    if (!selectedProductId) {
      toast.error('Please select a product');
      return;
    }

    const price = promotionPrice ? parseFloat(promotionPrice) : undefined;
    
    try {
      await addProductMutation.mutateAsync({
        promotionId,
        productId: selectedProductId,
        promotionPrice: price,
      });
      setAddProductDialogOpen(false);
      setSelectedProductId('');
      setPromotionPrice('');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const handleEditProduct = (product: { id: string; product_id: string; promotion_price: number | null }) => {
    setEditingProduct(product);
    setPromotionPrice(product.promotion_price?.toString() || '');
    setEditProductDialogOpen(true);
  };

  const handleUpdateProductPrice = async () => {
    if (!editingProduct) return;

    const price = promotionPrice ? parseFloat(promotionPrice) : 0;
    
    try {
      await updatePriceMutation.mutateAsync({
        promotionId,
        productId: editingProduct.product_id,
        promotionPrice: price,
      });
      setEditProductDialogOpen(false);
      setEditingProduct(null);
      setPromotionPrice('');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const handleRemoveProduct = async (productId: string) => {
    if (!confirm('Are you sure you want to remove this product from the promotion?')) {
      return;
    }

    try {
      await removeProductMutation.mutateAsync({
        promotionId,
        productId,
      });
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  const typeLabels: Record<string, string> = {
    price_override: 'Price Override',
    discount_percent: 'Discount %',
    discount_amount: 'Discount Amount',
    bundle: 'Bundle',
    other: 'Other',
  };

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
      <Card>
        <CardHeader>
          <CardTitle>Attachments</CardTitle>
        </CardHeader>
        <CardContent>
          <PromotionAttachmentsTab promotionId={promotionId} isEditMode={false} />
        </CardContent>
      </Card>

      {/* Products Section */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Products in Promotion</CardTitle>
          <Button onClick={() => setAddProductDialogOpen(true)}>
            <Plus className="size-4" />
            Add Product
          </Button>
        </CardHeader>
        <CardContent>
          {promotion.products && promotion.products.length > 0 ? (
            <div className="space-y-4">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-2 font-medium text-sm">Product Code</th>
                      <th className="text-left p-2 font-medium text-sm">Product Name</th>
                      <th className="text-right p-2 font-medium text-sm">List Price</th>
                      <th className="text-right p-2 font-medium text-sm">Promo Price</th>
                      <th className="text-right p-2 font-medium text-sm">Discount</th>
                      <th className="text-right p-2 font-medium text-sm">Discount %</th>
                      <th className="text-right p-2 font-medium text-sm">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {promotion.products.map((pp) => {
                      const listPrice = pp.product?.list_price || 0;
                      const promoPrice = pp.promotion_price || listPrice;
                      const discount = listPrice - promoPrice;
                      const discountPercent = listPrice > 0 ? (discount / listPrice) * 100 : 0;

                      return (
                        <tr key={pp.id} className="border-b">
                          <td className="p-2 text-sm">{pp.product?.product_code || '-'}</td>
                          <td className="p-2 text-sm">{pp.product?.product_name || '-'}</td>
                          <td className="p-2 text-sm text-right">
                            {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(listPrice)}
                          </td>
                          <td className="p-2 text-sm text-right">
                            {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(promoPrice)}
                          </td>
                          <td className="p-2 text-sm text-right">
                            {discount > 0 ? (
                              <Badge variant="success">
                                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(discount)}
                              </Badge>
                            ) : (
                              '-'
                            )}
                          </td>
                          <td className="p-2 text-sm text-right">
                            {discountPercent > 0 ? (
                              <Badge variant="info">{discountPercent.toFixed(1)}%</Badge>
                            ) : (
                              '-'
                            )}
                          </td>
                          <td className="p-2 text-right">
                            <div className="flex justify-end gap-2">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleEditProduct({
                                  id: pp.id,
                                  product_id: pp.product_id,
                                  promotion_price: pp.promotion_price ?? null,
                                })}
                              >
                                <Edit className="size-4" />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRemoveProduct(pp.product_id)}
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
                    })}
                  </tbody>
                </table>
              </div>
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
      <Dialog open={addProductDialogOpen} onOpenChange={setAddProductDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Product to Promotion</DialogTitle>
            <DialogDescription>
              Select a product and optionally set a promotion price.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
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
                      No available products
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Promotion Price (Optional)</Label>
              <Input
                type="number"
                step="0.01"
                placeholder="Leave empty to use list price"
                value={promotionPrice}
                onChange={(e) => setPromotionPrice(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setAddProductDialogOpen(false);
              setSelectedProductId('');
              setPromotionPrice('');
            }}>
              Cancel
            </Button>
            <Button
              onClick={handleAddProduct}
              disabled={!selectedProductId || addProductMutation.isPending}
            >
              {addProductMutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Adding...
                </>
              ) : (
                'Add Product'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Product Price Dialog */}
      <Dialog open={editProductDialogOpen} onOpenChange={setEditProductDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Promotion Price</DialogTitle>
            <DialogDescription>
              Update the promotion price for this product.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {editingProduct && (
              <div className="space-y-2">
                <Label>Promotion Price *</Label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="Enter promotion price"
                  value={promotionPrice}
                  onChange={(e) => setPromotionPrice(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  List Price: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(
                    promotion.products?.find(p => p.product_id === editingProduct.product_id)?.product?.list_price || 0
                  )}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setEditProductDialogOpen(false);
              setEditingProduct(null);
              setPromotionPrice('');
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
                'Update Price'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
