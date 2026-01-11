'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { useCreateStorageZone, useUpdateStorageZone } from '../hooks/useStorageZones';
import type { StorageZoneFormData } from '../types/storageZone.types';

const StorageZoneSchema = z.object({
  warehouse_id: z.string().uuid('Warehouse is required'),
  zone_code: z.string().min(1, 'Zone code is required').max(50),
  zone_name: z.string().max(150).optional().nullable(),
  zone_type: z.enum(['shelf', 'rack', 'bin', 'pallet']),
  capacity: z.number().int().positive('Capacity must be a positive number'),
  is_active: z.boolean().default(true),
});

interface StorageZoneFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  zoneId?: string;
}

export default function StorageZoneForm({ open, onOpenChange, zoneId }: StorageZoneFormProps) {
  const createMutation = useCreateStorageZone();
  const updateMutation = useUpdateStorageZone();

  const form = useForm<StorageZoneFormData>({
    resolver: zodResolver(StorageZoneSchema),
    defaultValues: {
      warehouse_id: '',
      zone_code: '',
      zone_name: '',
      zone_type: 'shelf',
      capacity: 0,
      is_active: true,
    },
  });

  useEffect(() => {
    if (open) {
      form.reset();
    }
  }, [open, form]);

  const onSubmit = async (data: StorageZoneFormData) => {
    try {
      if (zoneId) {
        await updateMutation.mutateAsync({ id: zoneId, data });
      } else {
        await createMutation.mutateAsync(data);
      }
      onOpenChange(false);
      form.reset();
    } catch (error) {
      // Error handled by mutation
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{zoneId ? 'Edit Storage Zone' : 'Create Storage Zone'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="warehouse_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Warehouse *</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select warehouse" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {/* TODO: Populate from warehouses */}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="zone_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Zone Code *</FormLabel>
                  <FormControl>
                    <Input placeholder="ZONE-001" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="zone_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Zone Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter zone name" {...field} value={field.value || ''} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="zone_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Zone Type *</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="shelf">Shelf</SelectItem>
                      <SelectItem value="rack">Rack</SelectItem>
                      <SelectItem value="bin">Bin</SelectItem>
                      <SelectItem value="pallet">Pallet</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="capacity"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Capacity *</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                {zoneId ? 'Update' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
