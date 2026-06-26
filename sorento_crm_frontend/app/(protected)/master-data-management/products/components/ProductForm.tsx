'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter, useSearchParams } from 'next/navigation';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { CategoryCombobox } from '../../shared/components/CategoryCombobox';
import { BrandCombobox } from '../../shared/components/BrandCombobox';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import { useCreateProduct, useUpdateProduct, useProduct, useProducts } from '../hooks/useProducts';
import { ProductSchema, type ProductSchemaType } from '../forms/product-schema';
import type { Product, ProductFormData } from '../types/product.types';
import { useProductCategorySelectQuery } from '../../shared/hooks/use-product-category-select-query';
import { useBrandSelectQuery } from '../../shared/hooks/use-brand-select-query';
import { useUOMSelectQuery } from '../../shared/hooks/use-uom-select-query';
import ProductSuppliersSection from './ProductSuppliersSection';
import ProductAttachmentsTab from './ProductAttachmentsTab';
import RecordNavigation from '@/components/common/RecordNavigation';

interface ProductFormProps {
  productId?: string;
  /** When provided, used as sole source for form reset (avoids cache/timing issues) */
  initialProduct?: Product | null;
  onSuccess?: () => void;
}

export default function ProductForm({ productId, initialProduct, onSuccess }: ProductFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isEditMode = !!productId;
  const { data: productFromQuery, isLoading: isLoadingProduct } = useProduct(productId || null);
  /** Use initialProduct when passed (from Edit page); otherwise use query result */
  const product = initialProduct ?? productFromQuery;
  const { data: categories } = useProductCategorySelectQuery();
  const { data: brands } = useBrandSelectQuery();
  const { data: uoms } = useUOMSelectQuery();
  const createMutation = useCreateProduct();
  const updateMutation = useUpdateProduct();

  const navigationParams = useMemo(() => {
    // Param names match the list GET (carried into the detail/edit URL by
    // buildDetailSearch): query / category_id / brand_id / status / sort+dir /
    // page (1-based) + limit.
    const search = searchParams.get('query') ?? '';
    const category = searchParams.get('category_id') ?? undefined;
    const brand = searchParams.get('brand_id') ?? undefined;
    const statusParam = searchParams.get('status') ?? 'all';
    const sortField = searchParams.get('sort') ?? 'created_at';
    const sortDir = searchParams.get('dir') ?? 'desc';
    const page = parseInt(searchParams.get('page') ?? '1', 10);
    const pageSize = parseInt(searchParams.get('limit') ?? '50', 10);
    return {
      pageIndex: Number.isNaN(page) ? 0 : Math.max(0, page - 1),
      pageSize: Number.isNaN(pageSize) || pageSize < 1 ? 50 : Math.min(pageSize, 500),
      sorting: [{ id: sortField, desc: sortDir === 'desc' }],
      searchQuery: search,
      category_id: category || undefined,
      brand_id: brand || undefined,
      status: (statusParam === 'active' || statusParam === 'inactive'
        ? statusParam
        : 'all') as 'active' | 'inactive' | 'all',
      price_min: undefined,
      price_max: undefined,
      item_type: undefined,
    };
  }, [searchParams]);

  const { data: navigationData } = useProducts(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  const navigationBasePath = '/master-data-management/products';
  const navigationQueryString = searchParams.toString();
  const handleNavigate = (id: string) => {
    router.push(
      `${navigationBasePath}/${id}/edit${navigationQueryString ? `?${navigationQueryString}` : ''}`,
    );
  };

  const form = useForm<ProductSchemaType>({
    resolver: zodResolver(ProductSchema),
    defaultValues: {
      product_code: '',
      product_name: '',
      description: '',
      category_id: '',
      brand_id: null,
      item_type: null,
      is_active: true,
      list_price: 0,
      cost_price: null,
      invoice_price: null,
      weight: null,
      dimensions_length: null,
      dimensions_width: null,
      dimensions_height: null,
      warranty_months: null,
      has_serial_tracking: false,
      has_batch_tracking: false,
      reorder_level: 10,
      reorder_quantity: 50,
      base_uom_id: '',
    },
    mode: 'onSubmit',
  });

  // Track which product we've initialized so we don't reset on every render.
  // Using a ref instead of state avoids Strict Mode timing issues (state updates can be
  // lost when Strict Mode unmounts before the effect runs).
  const lastInitializedProductIdRef = useRef<string | null>(null);

  // Reset init guard when productId changes or on unmount (fixes Strict Mode: ref must
  // be cleared on unmount so reset runs again after remount).
  useEffect(() => {
    lastInitializedProductIdRef.current = null;
    return () => {
      lastInitializedProductIdRef.current = null;
    };
  }, [productId]);

  // Load product data when editing - use useLayoutEffect so reset runs before paint,
  // avoiding any flash of empty Category/Brand. Runs synchronously (no Strict Mode cancel).
  useLayoutEffect(() => {
    if (!product || !isEditMode || lastInitializedProductIdRef.current === product.id) return;

    const categoryId = product.category_id
      ? String(product.category_id)
      : product.category?.id
        ? String(product.category.id)
        : '';
    const brandId = product.brand_id
      ? String(product.brand_id)
      : product.brand?.id
        ? String(product.brand.id)
        : null;
    const uomId = String(product.base_uom_id || '');

    form.reset({
      product_code: product.product_code,
      product_name: product.product_name,
      description: product.description || '',
      category_id: categoryId,
      brand_id: brandId,
      item_type: product.item_type || null,
      is_active: product.is_active,
      list_price: product.list_price,
      cost_price: product.cost_price || null,
      invoice_price: product.invoice_price || null,
      weight: product.weight || null,
      dimensions_length: product.dimensions_length || null,
      dimensions_width: product.dimensions_width || null,
      dimensions_height: product.dimensions_height || null,
      warranty_months: product.warranty_months || null,
      has_serial_tracking: product.has_serial_tracking,
      has_batch_tracking: product.has_batch_tracking,
      reorder_level: product.reorder_level,
      reorder_quantity: product.reorder_quantity,
      base_uom_id: uomId,
    });
    lastInitializedProductIdRef.current = product.id;
  }, [product, isEditMode, form]);

  // Auto-save draft to localStorage every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (form.formState.isDirty) {
        const formData = form.getValues();
        localStorage.setItem('product-form-draft', JSON.stringify(formData));
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [form]);

  const onSubmit = async (data: ProductSchemaType) => {
    try {
      // For update: send null for cleared optional fields (backend needs explicit null to set DB to NULL).
      // For create: omit optional fields when null (undefined).
      const toOptionalNumber = (v: number | string | null | undefined, forUpdate: boolean): number | null | undefined => {
        if (v != null && v !== '') {
          const n = typeof v === 'number' ? v : Number(v);
          if (!Number.isNaN(n)) return n;
        }
        return forUpdate ? null : undefined;
      };

      const formData: ProductFormData = {
        product_code: data.product_code,
        product_name: data.product_name,
        description: data.description || undefined,
        category_id: data.category_id,
        brand_id: data.brand_id ?? (isEditMode ? null : undefined),
        base_uom_id: data.base_uom_id,
        list_price: typeof data.list_price === 'number' ? data.list_price : Number(data.list_price),
        cost_price: toOptionalNumber(data.cost_price, isEditMode),
        invoice_price: toOptionalNumber(data.invoice_price, isEditMode),
        weight: toOptionalNumber(data.weight, isEditMode),
        dimensions_length: toOptionalNumber(data.dimensions_length, isEditMode),
        dimensions_width: toOptionalNumber(data.dimensions_width, isEditMode),
        dimensions_height: toOptionalNumber(data.dimensions_height, isEditMode),
        warranty_months: toOptionalNumber(data.warranty_months, isEditMode),
        has_serial_tracking: data.has_serial_tracking,
        has_batch_tracking: data.has_batch_tracking,
        reorder_level: data.reorder_level,
        reorder_quantity: data.reorder_quantity,
        item_type: data.item_type ?? (isEditMode ? null : undefined),
        is_active: data.is_active,
      };

      if (isEditMode && productId) {
        await updateMutation.mutateAsync({ id: productId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      localStorage.removeItem('product-form-draft');
      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/master-data-management/products');
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('Product form submission error:', error);
    }
  };

  // In edit mode, wait for product only. Category, Brand, UOM are fetched here and use
  // product.category / product.brand / product.base_uom as display fallback (same as UOM).
  if (isEditMode && product == null) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit, (errors) => {
          const first = Object.values(errors)[0]?.message;
          if (first) toast.error(first);
        })}
        className="space-y-6"
      >
        {isEditMode && productId && (
          <div className="flex justify-end">
            <RecordNavigation
              currentId={productId}
              items={navigationItems}
              basePath={navigationBasePath}
              onSelect={handleNavigate}
            />
          </div>
        )}
        <Tabs defaultValue="basic" className="w-full">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="basic">Basic Information</TabsTrigger>
            <TabsTrigger value="pricing">Pricing</TabsTrigger>
            <TabsTrigger value="specifications">Specifications</TabsTrigger>
            <TabsTrigger value="suppliers">Suppliers</TabsTrigger>
            <TabsTrigger value="attachments">Attachments</TabsTrigger>
          </TabsList>

          {/* Tab 1: Basic Information */}
          <TabsContent value="basic">
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="product_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Product Code *</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="PROD-001"
                          {...field}
                          disabled={isEditMode}
                        />
                      </FormControl>
                      <FormDescription>
                        Unique product identifier (alphanumeric, dashes, underscores only)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="product_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Product Name *</FormLabel>
                      <FormControl>
                        <Input placeholder="Enter product name" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Description</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Enter product description"
                          {...field}
                          value={field.value || ''}
                          rows={4}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="category_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Category *</FormLabel>
                        <FormControl>
                          <CategoryCombobox
                            value={field.value || ''}
                            onChange={field.onChange}
                            categories={categories}
                            productCategory={product?.category}
                            placeholder="Search category..."
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="brand_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Brand</FormLabel>
                        <FormControl>
                          <BrandCombobox
                            value={field.value}
                            onChange={field.onChange}
                            brands={brands}
                            productBrand={product?.brand}
                            placeholder="Search brand..."
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="item_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Item Type</FormLabel>
                        <Select
                          onValueChange={(value) => field.onChange(value === '__none__' ? null : value)}
                          value={field.value || '__none__'}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select item type" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="__none__">None</SelectItem>
                            <SelectItem value="product">Product</SelectItem>
                            <SelectItem value="bundle">Bundle</SelectItem>
                            <SelectItem value="service">Service</SelectItem>
                            <SelectItem value="other">Other</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="is_active"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Active Status</FormLabel>
                          <FormDescription>
                            Enable or disable this product
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 2: Pricing */}
          <TabsContent value="pricing">
            <Card>
              <CardHeader>
                <CardTitle>Pricing</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="list_price"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>List Price *</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          {...field}
                          value={field.value ?? ''}
                          onChange={(e) => {
                            const value = e.target.value;
                            if (value === '') {
                              field.onChange(0);
                            } else {
                              const numValue = parseFloat(value);
                              field.onChange(isNaN(numValue) ? 0 : numValue);
                            }
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="cost_price"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Cost Price</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          {...field}
                          value={field.value || ''}
                          onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                        />
                      </FormControl>
                      <FormDescription>
                        Internal cost price (hidden from viewers)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="invoice_price"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Invoice Price</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          {...field}
                          value={field.value || ''}
                          onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                        />
                      </FormControl>
                      <FormDescription>
                        Invoice price (hidden from viewers)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 3: Specifications */}
          <TabsContent value="specifications">
            <Card>
              <CardHeader>
                <CardTitle>Specifications</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="base_uom_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Base Unit of Measure *</FormLabel>
                      <FormControl>
                        <Select
                          onValueChange={field.onChange}
                          value={field.value || ''}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select base UOM" />
                          </SelectTrigger>
                          <SelectContent>
                            {uoms?.map((uom) => (
                              <SelectItem key={uom.id} value={uom.id}>
                                {uom.uom_code}
                              </SelectItem>
                            ))}
                            {product?.base_uom &&
                              !uoms?.some((uom) => uom.id === product.base_uom?.id) && (
                                <SelectItem
                                  key={product.base_uom.id}
                                  value={product.base_uom.id}
                                >
                                  {product.base_uom.uom_code}
                                </SelectItem>
                              )}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="weight"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Weight</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          {...field}
                          value={field.value || ''}
                          onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="dimensions_length"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Length</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value || ''}
                            onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="dimensions_width"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Width</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value || ''}
                            onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="dimensions_height"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Height</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            {...field}
                            value={field.value || ''}
                            onChange={(e) => field.onChange(e.target.value ? parseFloat(e.target.value) : null)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="warranty_months"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Warranty (Months)</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder="0"
                          {...field}
                          value={field.value || ''}
                          onChange={(e) => field.onChange(e.target.value ? parseInt(e.target.value) : null)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="has_serial_tracking"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Serial Tracking</FormLabel>
                          <FormDescription>
                            Track individual serial numbers
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="has_batch_tracking"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Batch Tracking</FormLabel>
                          <FormDescription>
                            Track batches with expiry dates
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="reorder_level"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Reorder Level</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="10"
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="reorder_quantity"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Reorder Quantity</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="50"
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 4: Suppliers */}
          <TabsContent value="suppliers">
            <ProductSuppliersSection
              productId={productId}
              isEditMode={isEditMode}
            />
          </TabsContent>

          {/* Tab 5: Attachments */}
          <TabsContent value="attachments">
            <ProductAttachmentsTab productId={productId} isEditMode={isEditMode} />
          </TabsContent>
        </Tabs>

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              isEditMode && productId
                ? router.push(`/master-data-management/products/${productId}`)
                : router.back()
            }
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="size-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="size-4" />
                {isEditMode ? 'Update Product' : 'Create Product'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
