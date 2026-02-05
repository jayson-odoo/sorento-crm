'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { useProduct, useProducts } from '../../hooks/useProducts';
import { formatDate } from '@/lib/helpers';
import { DataGrid } from '@/components/ui/data-grid';
import ProductAttachmentsTab from '../../components/ProductAttachmentsTab';
import ProductStockTab from './ProductStockTab';
import RecordNavigation from '../../../../../../components/common/RecordNavigation';

interface ProductDetailProps {
  productId: string;
}

export default function ProductDetail({ productId }: ProductDetailProps) {
  const router = useRouter();
  const { data: product, isLoading } = useProduct(productId);
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
      category_id: undefined,
      brand_id: undefined,
      status: 'all' as const,
    }),
    [],
  );
  const { data: navigationData } = useProducts(navigationParams);
  const navigationItems = navigationData?.data ?? [];

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
            basePath="/master-data-management/products"
          />
          <Button
            variant="outline"
            onClick={() => router.push(`/master-data-management/products/${productId}/edit`)}
          >
            <Edit className="size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => {
            // TODO: Implement delete with confirmation
            console.log('Delete product:', productId);
          }}>
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
                  {formatDate(new Date(product.created_at))}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Last Updated</p>
                <p className="font-medium text-sm">
                  {formatDate(new Date(product.updated_at))}
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
              <TabsTrigger value="related">Related Data</TabsTrigger>
              <TabsTrigger value="audit">Audit Trail</TabsTrigger>
            </TabsList>

            {/* Tab: Overview */}
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
                        <p className="font-medium">{product.product_code}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Product Name</p>
                        <p className="font-medium">{product.product_name}</p>
                      </div>
                      <div className="col-span-2">
                        <p className="text-muted-foreground">Description</p>
                        <p className="font-medium">
                          {product.description || '-'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">Pricing Summary</h3>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <p className="text-muted-foreground">List Price</p>
                        <p className="font-medium text-lg">
                          {new Intl.NumberFormat('en-US', {
                            style: 'currency',
                            currency: 'MYR',
                          }).format(product.list_price)}
                        </p>
                      </div>
                      {product.cost_price && (
                        <div>
                          <p className="text-muted-foreground">Cost Price</p>
                          <p className="font-medium text-lg">
                            {new Intl.NumberFormat('en-US', {
                              style: 'currency',
                              currency: 'MYR',
                            }).format(product.cost_price)}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">Specifications</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      {product.weight && (
                        <div>
                          <p className="text-muted-foreground">Weight</p>
                          <p className="font-medium">{product.weight}</p>
                        </div>
                      )}
                      {product.dimensions_length && (
                        <div>
                          <p className="text-muted-foreground">Dimensions</p>
                          <p className="font-medium">
                            {product.dimensions_length} × {product.dimensions_width} ×{' '}
                            {product.dimensions_height}
                          </p>
                        </div>
                      )}
                      {product.warranty_months && (
                        <div>
                          <p className="text-muted-foreground">Warranty</p>
                          <p className="font-medium">
                            {product.warranty_months} months
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  <div>
                    <h3 className="font-semibold mb-2">Tracking Flags</h3>
                    <div className="flex gap-4">
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

            {/* Tab: Related Data */}
            <TabsContent value="related">
              <Card>
                <CardHeader>
                  <CardTitle>Related Data</CardTitle>
                </CardHeader>
                <CardContent>
                  {/* TODO: Product suppliers, promotions, recent orders, attachments */}
                  <div className="text-sm text-muted-foreground">
                    Related data will be displayed here
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Tab: Audit Trail */}
            <TabsContent value="audit">
              <Card>
                <CardHeader>
                  <CardTitle>Audit Trail</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Created</p>
                      <p className="font-medium">
                        {formatDate(new Date(product.created_at))}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Last Modified</p>
                      <p className="font-medium">
                        {formatDate(new Date(product.updated_at))}
                      </p>
                    </div>
                    {/* TODO: Version history and change log */}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
