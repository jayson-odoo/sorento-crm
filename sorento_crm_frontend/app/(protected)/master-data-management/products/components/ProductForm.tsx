'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
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
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCreateProduct, useUpdateProduct, useProduct } from '../hooks/useProducts';
import { ProductSchema, type ProductSchemaType } from '../forms/product-schema';
import type { ProductFormData } from '../types/product.types';
import { useProductCategorySelectQuery } from '../../shared/hooks/use-product-category-select-query';
import { useBrandSelectQuery } from '../../shared/hooks/use-brand-select-query';
import { useUOMSelectQuery } from '../../shared/hooks/use-uom-select-query';
import ProductSuppliersSection from './ProductSuppliersSection';
import ProductAttachmentsTab from './ProductAttachmentsTab';

interface ProductFormProps {
  productId?: string;
  onSuccess?: () => void;
}

export default function ProductForm({ productId, onSuccess }: ProductFormProps) {
  const router = useRouter();
  const isEditMode = !!productId;
  const { data: product, isLoading: isLoadingProduct } = useProduct(productId || null);
  const { data: categories } = useProductCategorySelectQuery();
  const { data: brands } = useBrandSelectQuery();
  const { data: uoms } = useUOMSelectQuery();
  const createMutation = useCreateProduct();
  const updateMutation = useUpdateProduct();

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

  // Track if form has been initialized to prevent multiple resets
  const [formInitialized, setFormInitialized] = useState(false);

  // Load product data when editing - initialize form as soon as product data is available
  useEffect(() => {
    if (product && isEditMode && !formInitialized) {
      // Ensure values are strings for proper matching
      const categoryId = String(product.category_id || '');
      const brandId = product.brand_id ? String(product.brand_id) : null;
      const uomId = String(product.base_uom_id || '');

      // Initialize form immediately with product data
      // Select components will handle values even if options haven't loaded yet
      const timeoutId = setTimeout(() => {
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
        
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    }
  }, [product, isEditMode, form, formInitialized]);

  // Reset formInitialized when productId changes
  useEffect(() => {
    setFormInitialized(false);
  }, [productId]);

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
      // Transform data to ensure proper format - keep null values as null for optional fields
      const formData: ProductFormData = {
        product_code: data.product_code,
        product_name: data.product_name,
        description: data.description || undefined,
        category_id: data.category_id,
        brand_id: data.brand_id ?? undefined,
        base_uom_id: data.base_uom_id,
        list_price: typeof data.list_price === 'number' ? data.list_price : Number(data.list_price),
        cost_price: data.cost_price ? (typeof data.cost_price === 'number' ? data.cost_price : Number(data.cost_price)) : undefined,
        invoice_price: data.invoice_price ? (typeof data.invoice_price === 'number' ? data.invoice_price : Number(data.invoice_price)) : undefined,
        weight: data.weight ?? undefined,
        dimensions_length: data.dimensions_length ?? undefined,
        dimensions_width: data.dimensions_width ?? undefined,
        dimensions_height: data.dimensions_height ?? undefined,
        warranty_months: data.warranty_months ?? undefined,
        has_serial_tracking: data.has_serial_tracking,
        has_batch_tracking: data.has_batch_tracking,
        reorder_level: data.reorder_level,
        reorder_quantity: data.reorder_quantity,
        item_type: data.item_type ?? undefined,
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

  if (isEditMode && isLoadingProduct) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Tabs defaultValue="basic" className="w-full">
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="basic">Basic Information</TabsTrigger>
            <TabsTrigger value="pricing">Pricing</TabsTrigger>
            <TabsTrigger value="specifications">Specifications</TabsTrigger>
            <TabsTrigger value="uom">Unit of Measure</TabsTrigger>
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
                    render={({ field }) => {
                      const selectedCategory =
                        categories?.find((cat) => cat.id === field.value) ||
                        (product?.category
                          ? {
                              id: product.category.id,
                              category_code: product.category.category_code,
                            }
                          : null);
                      return (
                        <FormItem>
                          <FormLabel>Category *</FormLabel>
                          <Select
                            onValueChange={field.onChange}
                            value={field.value || ''}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select category" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {categories?.map((category) => (
                                <SelectItem key={category.id} value={category.id}>
                                  {category.category_code}
                                </SelectItem>
                              ))}
                              {/* Include product's category if not in the list (e.g., inactive) */}
                              {product?.category &&
                                !categories?.some(
                                  (cat) => cat.id === product.category?.id
                                ) && (
                                  <SelectItem
                                    key={product.category.id}
                                    value={product.category.id}
                                  >
                                    {product.category.category_code}
                                  </SelectItem>
                                )}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      );
                    }}
                  />

                  <FormField
                    control={form.control}
                    name="brand_id"
                    render={({ field }) => {
                      const selectedBrand =
                        brands?.find((brand) => brand.id === field.value) ||
                        (product?.brand && field.value
                          ? {
                              id: product.brand.id,
                              brand_code: product.brand.brand_code,
                            }
                          : null);
                      const displayValue = field.value
                        ? selectedBrand?.brand_code || ''
                        : 'None';
                      return (
                        <FormItem>
                          <FormLabel>Brand</FormLabel>
                          <Select
                            onValueChange={(value) =>
                              field.onChange(value === '__none__' ? null : value)
                            }
                            value={field.value || '__none__'}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select brand" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="__none__">None</SelectItem>
                              {brands?.map((brand) => (
                                <SelectItem key={brand.id} value={brand.id}>
                                  {brand.brand_code}
                                </SelectItem>
                              ))}
                              {/* Include product's brand if not in the list (e.g., inactive) */}
                              {product?.brand &&
                                field.value &&
                                !brands?.some(
                                  (brand) => brand.id === product.brand?.id
                                ) && (
                                  <SelectItem
                                    key={product.brand.id}
                                    value={product.brand.id}
                                  >
                                    {product.brand.brand_code}
                                  </SelectItem>
                                )}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      );
                    }}
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

                {/* TODO: Price History Table and Price Trend Chart */}
                <div className="text-sm text-muted-foreground">
                  Price history and trend chart will be displayed here
                </div>
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
                <div className="grid grid-cols-3 gap-4">
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
                </div>

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

          {/* Tab 4: Unit of Measure */}
          <TabsContent value="uom">
            <Card>
              <CardHeader>
                <CardTitle>Unit of Measure</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="base_uom_id"
                  render={({ field }) => {
                    const selectedUOM =
                      uoms?.find((uom) => uom.id === field.value) ||
                      (product?.base_uom
                        ? {
                            id: product.base_uom.id,
                            uom_code: product.base_uom.uom_code,
                          }
                        : null);
                    return (
                      <FormItem>
                        <FormLabel>Base Unit of Measure *</FormLabel>
                        <Select
                          onValueChange={field.onChange}
                          value={field.value || ''}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select base UOM" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {uoms?.map((uom) => (
                              <SelectItem key={uom.id} value={uom.id}>
                                {uom.uom_code}
                              </SelectItem>
                            ))}
                            {/* Include product's UOM if not in the list */}
                            {product?.base_uom &&
                              !uoms?.some(
                                (uom) => uom.id === product.base_uom?.id
                              ) && (
                                <SelectItem
                                  key={product.base_uom.id}
                                  value={product.base_uom.id}
                                >
                                  {product.base_uom.uom_code}
                                </SelectItem>
                              )}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    );
                  }}
                />

                {/* TODO: Alternative UOMs table with conversion factors */}
                <div className="text-sm text-muted-foreground">
                  Alternative UOMs table will be displayed here
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tab 5: Suppliers */}
          <TabsContent value="suppliers">
            <ProductSuppliersSection
              productId={productId}
              isEditMode={isEditMode}
            />
          </TabsContent>

          {/* Tab 6: Attachments */}
          <TabsContent value="attachments">
            <ProductAttachmentsTab productId={productId} isEditMode={isEditMode} />
          </TabsContent>
        </Tabs>

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.back()}
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
