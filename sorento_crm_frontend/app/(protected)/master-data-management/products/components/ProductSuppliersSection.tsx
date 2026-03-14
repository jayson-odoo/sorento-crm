'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, LoaderCircleIcon, Save } from 'lucide-react';
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
import { getProductSuppliersByProductId, createProductSupplier, updateProductSupplier, deleteProductSupplier } from '../../../procurement-management/product-suppliers/services/productSupplierService';
import { useSupplierSelectQuery } from '../../../procurement-management/suppliers/hooks/useSupplierSelectQuery';
import { toast } from 'sonner';
import type { ProductSupplier } from '../../../procurement-management/product-suppliers/types/productSupplier.types';

function ProductSupplierRow({
  ps,
  onUpdateLeadTime,
  onRemove,
  isUpdating,
  isDeleting,
}: {
  ps: ProductSupplier;
  onUpdateLeadTime: (days: number) => void;
  onRemove: () => void;
  isUpdating: boolean;
  isDeleting: boolean;
}) {
  const currentDays = ps.standard_lead_time_days ?? ps.lead_time_days ?? 0;
  const [leadTimeInput, setLeadTimeInput] = useState(String(currentDays));
  const [hasChange, setHasChange] = useState(false);

  useEffect(() => {
    setLeadTimeInput(String(currentDays));
  }, [currentDays]);

  const handleLeadTimeBlur = () => {
    const num = parseInt(leadTimeInput, 10);
    if (!hasChange) return;
    if (isNaN(num) || num < 0) {
      setLeadTimeInput(String(currentDays));
      setHasChange(false);
      return;
    }
    onUpdateLeadTime(num);
    setHasChange(false);
  };

  const handleLeadTimeKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      (e.target as HTMLInputElement).blur();
    }
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant="secondary">
          {ps.supplier?.supplier_code || 'N/A'}
        </Badge>
        <span className="text-sm font-medium">
          {ps.supplier?.supplier_name || 'Unknown Supplier'}
        </span>
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground whitespace-nowrap">Lead time (days)</Label>
          <Input
            type="number"
            min={0}
            className="w-20 h-8"
            value={leadTimeInput}
            onChange={(e) => {
              setLeadTimeInput(e.target.value);
              setHasChange(true);
            }}
            onBlur={handleLeadTimeBlur}
            onKeyDown={handleLeadTimeKeyDown}
            disabled={isUpdating}
          />
          {hasChange && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8"
              onClick={() => {
                const num = parseInt(leadTimeInput, 10);
                if (!isNaN(num) && num >= 0) {
                  onUpdateLeadTime(num);
                  setHasChange(false);
                }
              }}
              disabled={isUpdating}
            >
              {isUpdating ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Save className="size-4" />}
            </Button>
          )}
        </div>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRemove}
        disabled={isDeleting}
      >
        {isDeleting ? (
          <LoaderCircleIcon className="size-4 animate-spin" />
        ) : (
          <Trash2 className="size-4 text-destructive" />
        )}
      </Button>
    </div>
  );
}

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
  const { data: suppliers = [] } = useSupplierSelectQuery();

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

  // Update lead time mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, standard_lead_time_days }: { id: string; standard_lead_time_days: number }) =>
      updateProductSupplier(id, { standard_lead_time_days }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-suppliers', productId] });
      toast.success('Lead time updated');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update lead time');
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
              <ProductSupplierRow
                key={ps.id}
                ps={ps}
                onUpdateLeadTime={(days) =>
                  updateMutation.mutate({ id: ps.id, standard_lead_time_days: days })
                }
                onRemove={() => handleRemoveSupplier(ps.id)}
                isUpdating={updateMutation.isPending}
                isDeleting={deleteMutation.isPending}
              />
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
