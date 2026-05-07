'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Edit, Trash2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { useProduct, useProducts } from '../../hooks/useProducts';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import ProductAttachmentsTab from '../../components/ProductAttachmentsTab';
import ProductStockTab from './ProductStockTab';
import ProductSuppliersTab from './ProductSuppliersTab';
import ProductDeleteDialog from '../../components/product-delete-dialog';
import RecordNavigation from '../../../../../../components/common/RecordNavigation';
import AuditTrail from '@/components/audit/AuditTrail';

interface ProductDetailProps {
  productId: string;
}

export default function ProductDetail({ productId }: ProductDetailProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const { data: product, isLoading } = useProduct(productId);

  const navigationParams = useMemo(() => {
    const search = searchParams.get('search') ?? '';
    const category = searchParams.get('category') ?? undefined;
    const brand = searchParams.get('brand') ?? undefined;
    const statusParam = searchParams.get('status') ?? 'all';
    const sortField = searchParams.get('sort') ?? 'created_at';
    const sortDir = searchParams.get('sortDir') ?? 'desc';
    const page = parseInt(searchParams.get('page') ?? '0', 10);
    const pageSize = parseInt(searchParams.get('pageSize') ?? '50', 10);
    return {
      pageIndex: Number.isNaN(page) ? 0 : Math.max(0, page),
      pageSize: Number.isNaN(pageSize) || pageSize < 1 ? 50 : Math.min(pageSize, 500),
      sorting: [{ id: sortField, desc: sortDir === 'desc' }],
      searchQuery: search,
      category_id: category || undefined,
      brand_id: brand || undefined,
      status: (statusParam === 'active' || statusParam === 'inactive'
        ? statusParam
        : 'all') as 'active' | 'inactive' | 'all',
    };
  }, [searchParams]);

  const { data: navigationData } = useProducts(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  const navigationBasePath = '/master-data-management/products';
  const navigationQueryString = searchParams.toString();
  const handleNavigate = (id: string) => {
    router.push(
      `${navigationBasePath}/${id}${navigationQueryString ? `?${navigationQueryString}` : ''}`,
    );
  };

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
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{product.product_name}</h1>
            <Badge
              variant={product.is_active ? 'success' : 'secondary'}
              appearance="ghost"
            >
              {product.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Product Code: {product.product_code}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={productId}
            items={navigationItems}
            basePath={navigationBasePath}
            onSelect={handleNavigate}
          />
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
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="stock">Stock</TabsTrigger>
              <TabsTrigger value="attachments">Attachments</TabsTrigger>
              <TabsTrigger value="suppliers">Suppliers</TabsTrigger>
              <TabsTrigger value="audit">Audit Trail</TabsTrigger>
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
                        <p className="font-medium">{product.weight != null ? product.weight : '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Dimensions (L × W × H)</p>
                        <p className="font-medium">
                          {product.dimensions_length != null &&
                          product.dimensions_width != null &&
                          product.dimensions_height != null
                            ? `${product.dimensions_length} × ${product.dimensions_width} × ${product.dimensions_height}`
                            : '-'}
                        </p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Warranty (Months)</p>
                        <p className="font-medium">{product.warranty_months != null ? product.warranty_months : '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Reorder Level</p>
                        <p className="font-medium">{product.reorder_level != null ? product.reorder_level : '-'}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Reorder Quantity</p>
                        <p className="font-medium">{product.reorder_quantity != null ? product.reorder_quantity : '-'}</p>
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

            {/* Tab: Attachments */}
            <TabsContent value="attachments">
              <ProductAttachmentsTab productId={productId} isEditMode={false} />
            </TabsContent>

            {/* Tab: Suppliers */}
            <TabsContent value="suppliers">
              <ProductSuppliersTab productId={productId} />
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
