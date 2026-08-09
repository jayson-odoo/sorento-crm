'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Boxes,
  Edit,
  FileText,
  GitBranch,
  Paperclip,
  Receipt,
  ScrollText,
  Tag,
  Trash2,
  Truck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { useProduct, useProductPurchaseHistory } from '../../hooks/useProducts';
import { formatDateSafe, formatDateTimeInMalaysia } from '@/lib/helpers';
import { useQuery } from '@tanstack/react-query';
import ProductAttachmentsTab from '../../components/ProductAttachmentsTab';
import ProductStockTab from './ProductStockTab';
import ProductPurchaseHistoryTab from './ProductPurchaseHistoryTab';
import ProductSuppliersTab from './ProductSuppliersTab';
import ProductPromotionsTab from './ProductPromotionsTab';
import ProductVariantsTab from './ProductVariantsTab';
import { useProductAttachmentsByProduct } from '../../../product-attachments/hooks/useProductAttachments';
import { getPromotionsByProductId } from '@/app/(protected)/marketing-management/promotions/services/promotionService';
import ProductDeleteDialog from '../../components/product-delete-dialog';
import ProductNavigation from './ProductNavigation';
import AuditTrail from '@/components/audit/AuditTrail';
import FieldAttachmentTooltip from './FieldAttachmentTooltip';
import { NO_CURRENCY_NOTE, formatUnitCost } from '../lib/cost';

interface ProductDetailProps {
  productId: string;
}

export default function ProductDetail({ productId }: ProductDetailProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const { data: product, isLoading } = useProduct(productId);

  // Tab badge counts — same hooks the tab content components use, so React
  // Query dedupes the request when the user opens the tab.
  const { data: attachmentsData } = useProductAttachmentsByProduct(productId || null);
  const attachmentsCount = Array.isArray(attachmentsData) ? attachmentsData.length : 0;
  const { data: promotionsData } = useQuery({
    queryKey: ['product-promotions', productId],
    queryFn: () => getPromotionsByProductId(productId),
    enabled: !!productId,
  });
  const promotionsCount = Array.isArray(promotionsData) ? promotionsData.length : 0;
  // Same query the Purchase History tab reads, so the Overview's cost and the orders that
  // prove it can never disagree.
  const { data: purchaseHistory } = useProductPurchaseHistory(productId || null);
  const purchaseCost = purchaseHistory?.cost ?? null;
  const variantsCount = Array.isArray(product?.variants) ? product.variants.length : 0;

  const navigationBasePath = '/master-data-management/products';
  const navigationQueryString = searchParams.toString();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!product) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Product not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/master-data-management/products')}
          className="mt-4"
        >
          <ArrowLeft className="size-4" />
          Back to Products
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1 min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold break-words min-w-0">{product.product_name}</h1>
            <Badge
              variant={product.is_active ? 'success' : 'secondary'}
              appearance="ghost"
            >
              {product.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground break-words">
            Product Code: {product.product_code}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ProductNavigation productId={productId} />
          <Button
            variant="outline"
            onClick={() =>
              router.push(
                `${navigationBasePath}/${productId}/edit${navigationQueryString ? `?${navigationQueryString}` : ''}`,
              )
            }
          >
            <Edit className="size-4" />
            Edit
          </Button>
          <Button
            variant="destructive"
            onClick={() => setDeleteDialogOpen(true)}
          >
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Sidebar - Quick Info */}
        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle>Quick Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">Category</p>
                <p className="font-medium">
                  {product.category?.category_name || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Brand</p>
                <p className="font-medium">
                  {product.brand?.brand_name || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">List Price</p>
                <p className="font-medium text-lg">
                  {new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: 'MYR',
                  }).format(product.list_price)}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge
                  variant={product.is_active ? 'success' : 'secondary'}
                  appearance="ghost"
                >
                  {product.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Created</p>
                <p className="font-medium text-sm">
                  {formatDateTimeInMalaysia(product.created_at)}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Last Updated</p>
                <p className="font-medium text-sm">
                  {product.updated_at
                    ? formatDateTimeInMalaysia(product.updated_at)
                    : '-'}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Content - Tabs */}
        <div className="lg:col-span-3">
          <Tabs defaultValue="overview" className="w-full">
            {/* Same underlined strip the user detail page uses, so a record's tabs look the
                same wherever you are in the system rather than one screen per style. */}
            <TabsList variant="line" className="mb-5 w-full justify-start overflow-x-auto">
              <TabsTrigger value="overview">
                <FileText />
                <span>Overview</span>
              </TabsTrigger>
              <TabsTrigger value="stock">
                <Boxes />
                <span>Stock</span>
              </TabsTrigger>
              <TabsTrigger value="purchases">
                <Receipt />
                <span>Purchase History</span>
              </TabsTrigger>
              <TabsTrigger value="attachments">
                <Paperclip />
                <span>Attachments{attachmentsCount ? ` (${attachmentsCount})` : ''}</span>
              </TabsTrigger>
              <TabsTrigger value="suppliers">
                <Truck />
                <span>Suppliers</span>
              </TabsTrigger>
              <TabsTrigger value="promotions">
                <Tag />
                <span>Promotions{promotionsCount ? ` (${promotionsCount})` : ''}</span>
              </TabsTrigger>
              <TabsTrigger value="variants">
                <GitBranch />
                <span>Variants{variantsCount ? ` (${variantsCount})` : ''}</span>
              </TabsTrigger>
              <TabsTrigger value="audit">
                <ScrollText />
                <span>Audit Trail</span>
              </TabsTrigger>
            </TabsList>

            {/* Tab: Overview - always show all fields from edit view regardless of value */}
            <TabsContent value="overview">
              <Card>
                <CardHeader>
                  <CardTitle>Overview</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <h3 className="font-semibold mb-2">Basic Information</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-muted-foreground">Product Code</p>
                        <p className="font-medium">{product.product_code || '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Product Name</p>
                        <p className="font-medium">{product.product_name || '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Category</p>
                        <p className="font-medium">{product.category?.category_code ?? product.category?.category_name ?? '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Brand</p>
                        <p className="font-medium">{product.brand?.brand_code ?? product.brand?.brand_name ?? '-'}</p>
                      </div>
                      <div className="col-span-2">
                        <p className="text-muted-foreground">Description</p>
                        <p className="font-medium">{product.description || '-'}</p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">Pricing Summary</h3>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <p className="text-muted-foreground">List Price</p>
                        <p className="font-medium text-lg">
                          {product.list_price != null
                            ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'MYR' }).format(product.list_price)
                            : '-'}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Cost Price</p>
                        <p className="font-medium text-lg">
                          {product.cost_price != null
                            ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'MYR' }).format(product.cost_price)
                            : '-'}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Invoice Price</p>
                        <p className="font-medium text-lg">
                          {product.invoice_price != null
                            ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'MYR' }).format(product.invoice_price)
                            : '-'}
                        </p>
                      </div>
                    </div>

                    {/* Cost Price above is a figure somebody typed. This one is money that
                        actually moved, and it names the order it came from - a cost with no
                        provenance cannot be checked, and the planning that runs on it cannot
                        be trusted either. */}
                    <div className="mt-4 rounded-lg border border-border bg-muted/30 p-3 text-sm">
                      <p className="text-muted-foreground">Last purchase price</p>
                      {purchaseCost?.status === 'ok' ? (
                        <>
                          <p className="text-lg font-medium">
                            {formatUnitCost(purchaseCost.unit_cost, purchaseCost.currency)}
                            <span className="ms-1 text-xs font-normal text-muted-foreground">
                              per unit
                            </span>
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {purchaseCost.po_number} ·{' '}
                            {purchaseCost.supplier_name ?? 'no supplier on the order'} ·{' '}
                            {formatDateSafe(purchaseCost.issue_date)}
                            {purchaseCost.currency ? '' : ` · ${NO_CURRENCY_NOTE}`}
                          </p>
                        </>
                      ) : (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {purchaseCost?.status === 'no_price_recorded'
                            ? 'Purchased before, but no unit cost was recorded on any order.'
                            : 'Never purchased, so there is no cost from history.'}
                        </p>
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">Specifications</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-muted-foreground">Base UOM</p>
                        <p className="font-medium">{product.base_uom?.uom_code ?? '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Weight</p>
                        <p className="font-medium flex items-center">
                          {product.weight != null ? product.weight : '-'}
                          <FieldAttachmentTooltip
                            productId={productId}
                            fieldKeys={['weight']}
                            fieldLabel="Weight"
                            fieldAttachments={product.field_attachments}
                          />
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Dimensions (L × W × H)</p>
                        <p className="font-medium flex items-center">
                          {product.dimensions_length != null &&
                          product.dimensions_width != null &&
                          product.dimensions_height != null
                            ? `${product.dimensions_length} × ${product.dimensions_width} × ${product.dimensions_height}`
                            : '-'}
                          <FieldAttachmentTooltip
                            productId={productId}
                            fieldKeys={['dimensions_length', 'dimensions_width', 'dimensions_height']}
                            fieldLabel="Dimensions (L × W × H)"
                            fieldAttachments={product.field_attachments}
                          />
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Warranty (Months)</p>
                        <p className="font-medium flex items-center">
                          {product.warranty_months != null ? product.warranty_months : '-'}
                          <FieldAttachmentTooltip
                            productId={productId}
                            fieldKeys={['warranty_months']}
                            fieldLabel="Warranty (Months)"
                            fieldAttachments={product.field_attachments}
                          />
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Reorder Level</p>
                        <p className="font-medium flex items-center">
                          {product.reorder_level != null ? product.reorder_level : '-'}
                          <FieldAttachmentTooltip
                            productId={productId}
                            fieldKeys={['reorder_level']}
                            fieldLabel="Reorder Level"
                            fieldAttachments={product.field_attachments}
                          />
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Reorder Quantity</p>
                        <p className="font-medium flex items-center">
                          {product.reorder_quantity != null ? product.reorder_quantity : '-'}
                          <FieldAttachmentTooltip
                            productId={productId}
                            fieldKeys={['reorder_quantity']}
                            fieldLabel="Reorder Quantity"
                            fieldAttachments={product.field_attachments}
                          />
                        </p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">Tracking Flags</h3>
                    <div className="flex flex-wrap gap-4">
                      <Badge
                        variant={product.has_serial_tracking ? 'success' : 'secondary'}
                      >
                        Serial Tracking: {product.has_serial_tracking ? 'Yes' : 'No'}
                      </Badge>
                      <Badge
                        variant={product.has_batch_tracking ? 'success' : 'secondary'}
                      >
                        Batch Tracking: {product.has_batch_tracking ? 'Yes' : 'No'}
                      </Badge>
                      <Badge
                        variant={product.is_discontinued ? 'destructive' : 'secondary'}
                        title="Auto-derived: True when description starts with ****"
                      >
                        Discontinued: {product.is_discontinued ? 'Yes' : 'No'}
                      </Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Tab: Stock */}
            <TabsContent value="stock">
              <ProductStockTab productId={productId} />
            </TabsContent>

            {/* Tab: Purchase History */}
            <TabsContent value="purchases">
              <ProductPurchaseHistoryTab productId={productId} />
            </TabsContent>

            {/* Tab: Attachments */}
            <TabsContent value="attachments">
              <ProductAttachmentsTab productId={productId} isEditMode={false} />
            </TabsContent>

            {/* Tab: Suppliers */}
            <TabsContent value="suppliers">
              <ProductSuppliersTab productId={productId} />
            </TabsContent>

            {/* Tab: Promotions */}
            <TabsContent value="promotions">
              <ProductPromotionsTab productId={productId} listPrice={product.list_price} />
            </TabsContent>

            {/* Tab: Variants */}
            <TabsContent value="variants">
              <ProductVariantsTab
                productId={product.id}
                productCode={product.product_code}
                variantOf={product.variant_of}
                variants={product.variants}
                variantLinkManual={product.variant_link_manual}
              />
            </TabsContent>

            {/* Tab: Audit Trail */}
            <TabsContent value="audit">
              <AuditTrail
                entityType="product"
                entityId={productId}
                title="Audit Trail"
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <ProductDeleteDialog
        open={deleteDialogOpen}
        closeDialog={() => setDeleteDialogOpen(false)}
        product={{
          id: product.id,
          product_code: product.product_code,
          product_name: product.product_name,
          list_price: product.list_price,
          is_active: product.is_active,
          created_at: product.created_at,
        }}
        onSuccess={() => router.push('/master-data-management/products')}
      />
    </div>
  );
}
