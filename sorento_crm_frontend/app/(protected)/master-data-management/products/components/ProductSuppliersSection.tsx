'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getProductSuppliersByProductId, createProductSupplier, deleteProductSupplier } from '../../../procurement-management/product-suppliers/services/productSupplierService';
import { useSuppliers } from '../../../procurement-management/suppliers/hooks/useSuppliers';
import { toast } from 'sonner';
import type { ProductSupplier } from '../../../procurement-management/product-suppliers/types/productSupplier.types';

interface ProductSuppliersSectionProps {
  productId: string | undefined;
  isEditMode: boolean;
}

export default function ProductSuppliersSection({
  productId,
  isEditMode,
}: ProductSuppliersSectionProps) {
  const queryClient = useQueryClient();
  const [selectedSupplierId, setSelectedSupplierId] = useState<string>('');
  const [leadTimeDays, setLeadTimeDays] = useState<string>('');

  // Fetch existing product suppliers
  const { data: productSuppliers, isLoading: isLoadingSuppliers } = useQuery({
    queryKey: ['product-suppliers', productId],
    queryFn: () => {
      if (!productId) throw new Error('Product ID is required');
      return getProductSuppliersByProductId(productId);
    },
    enabled: !!productId && isEditMode,
  });

  // Fetch all suppliers for the dropdown
  const { data: suppliersData } = useSuppliers({
    pageIndex: 0,
    pageSize: 1000,
    sorting: [],
    searchQuery: '',
  });
  const suppliers = suppliersData?.data || [];

  // Create mutation
  const createMutation = useMutation({
    mutationFn: ({ supplierId, leadTime }: { supplierId: string; leadTime: number }) => {
      if (!productId) throw new Error('Product ID is required');
      return createProductSupplier({
        product_id: productId,
        supplier_id: supplierId,
        standard_lead_time_days: leadTime,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-suppliers', productId] });
      setSelectedSupplierId('');
      setLeadTimeDays('');
      toast.success('Supplier added successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to add supplier');
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProductSupplier(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-suppliers', productId] });
      toast.success('Supplier removed successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to remove supplier');
    },
  });

  const handleAddSupplier = () => {
    if (!selectedSupplierId) {
      toast.error('Please select a supplier');
      return;
    }

    const leadTime = parseInt(leadTimeDays, 10);
    if (isNaN(leadTime) || leadTime < 0) {
      toast.error('Please enter a valid lead time (number of days)');
      return;
    }

    // Check if supplier is already added
    const alreadyAdded = productSuppliers?.some(
      (ps) => ps.supplier_id === selectedSupplierId
    );
    if (alreadyAdded) {
      toast.error('This supplier is already added');
      return;
    }

    createMutation.mutate({ supplierId: selectedSupplierId, leadTime });
  };

  const handleRemoveSupplier = (id: string) => {
    deleteMutation.mutate(id);
  };

  // Get available suppliers (not already added)
  const availableSuppliers = suppliers.filter(
    (supplier) =>
      !productSuppliers?.some((ps) => ps.supplier_id === supplier.id)
  );

  if (!isEditMode) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Suppliers</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Save the product first to configure suppliers.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Suppliers</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Add Supplier Section */}
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Supplier *</Label>
              <Select value={selectedSupplierId} onValueChange={setSelectedSupplierId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a supplier to add" />
                </SelectTrigger>
                <SelectContent>
                  {availableSuppliers.map((supplier) => (
                    <SelectItem key={supplier.id} value={supplier.id}>
                      {supplier.supplier_code} - {supplier.supplier_name}
                    </SelectItem>
                  ))}
                  {availableSuppliers.length === 0 && (
                    <SelectItem value="__no_suppliers__" disabled>
                      No available suppliers
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Lead Time (Days) *</Label>
              <Input
                type="number"
                placeholder="e.g., 7"
                value={leadTimeDays}
                onChange={(e) => setLeadTimeDays(e.target.value)}
                min="0"
              />
            </div>
          </div>
          <Button
            type="button"
            onClick={handleAddSupplier}
            disabled={!selectedSupplierId || !leadTimeDays || createMutation.isPending}
          >
            {createMutation.isPending ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              <Plus className="size-4" />
            )}
            Add Supplier
          </Button>
        </div>

        {/* Existing Suppliers List */}
        {isLoadingSuppliers ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : productSuppliers && productSuppliers.length > 0 ? (
          <div className="space-y-2">
            {productSuppliers.map((ps) => (
              <div
                key={ps.id}
                className="flex items-center justify-between rounded-lg border p-3"
              >
                <div className="flex items-center gap-3">
                  <Badge variant="secondary">
                    {ps.supplier?.supplier_code || 'N/A'}
                  </Badge>
                  <span className="text-sm font-medium">
                    {ps.supplier?.supplier_name || 'Unknown Supplier'}
                  </span>
                  {(ps.standard_lead_time_days !== undefined || ps.lead_time_days !== undefined) && (
                    <Badge variant="outline" className="text-xs">
                      Lead Time: {ps.standard_lead_time_days ?? ps.lead_time_days} days
                    </Badge>
                  )}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRemoveSupplier(ps.id)}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? (
                    <LoaderCircleIcon className="size-4 animate-spin" />
                  ) : (
                    <Trash2 className="size-4 text-destructive" />
                  )}
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No suppliers configured for this product.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
