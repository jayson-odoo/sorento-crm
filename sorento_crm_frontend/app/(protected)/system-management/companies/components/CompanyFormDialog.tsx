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
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { CompanySchema } from '../forms/company-schema';
import { useCreateCompany, useUpdateCompany, useCompany } from '../hooks/useCompanies';
import type { CompanyFormData } from '../types/company.types';

interface CompanyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  companyId?: string;
}

export default function CompanyFormDialog({
  open,
  onOpenChange,
  companyId,
}: CompanyFormDialogProps) {
  const { data: company } = useCompany(companyId || null);
  const createMutation = useCreateCompany();
  const updateMutation = useUpdateCompany();

  const form = useForm<z.infer<typeof CompanySchema>>({
    resolver: zodResolver(CompanySchema),
    mode: 'onTouched',
    defaultValues: {
      name: '',
      code: '',
      is_active: true,
      autocount_ref: '',
      logo_url: '',
    },
  });

  useEffect(() => {
    if (open) {
      if (companyId && company) {
        form.reset({
          name: company.name,
          code: company.code,
          is_active: company.is_active,
          autocount_ref: company.autocount_ref ?? '',
          logo_url: company.logo_url ?? '',
        });
      } else {
        form.reset({
          name: '',
          code: '',
          is_active: true,
          autocount_ref: '',
          logo_url: '',
        });
      }
    }
  }, [open, form, companyId, company]);

  const onSubmit = async (data: z.infer<typeof CompanySchema>) => {
    try {
      const formData: CompanyFormData = {
        name: data.name,
        code: data.code,
        is_active: data.is_active,
        autocount_ref: data.autocount_ref ? data.autocount_ref : null,
        logo_url: data.logo_url ? data.logo_url : null,
      };

      if (companyId) {
        await updateMutation.mutateAsync({ id: companyId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }
      onOpenChange(false);
      form.reset();
    } catch {
      // Error surfaced by the mutation's onError toast.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{companyId ? 'Edit Company' : 'Create Company'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Company Name *</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter company name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Company Code *</FormLabel>
                  <FormControl>
                    <Input placeholder="SRT" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="autocount_ref"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>AutoCount Reference</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="AutoCount company reference"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="logo_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Logo URL</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="https://…/logo.png"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
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
                    <FormLabel className="text-base">Active</FormLabel>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {companyId ? 'Update' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
