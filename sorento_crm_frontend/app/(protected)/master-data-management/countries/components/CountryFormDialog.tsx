'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { useCreateCountry, useUpdateCountry } from '../hooks/useCountries';
import { CountrySchema, type CountrySchemaType } from '../forms/country-schema';
import type { Country } from '../types/country.types';

interface CountryFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  country?: Country | null;
}

const EMPTY: CountrySchemaType = {
  code: '',
  name: '',
  is_active: true,
};

export default function CountryFormDialog({
  open,
  onOpenChange,
  country,
}: CountryFormDialogProps) {
  const isEditMode = !!country;
  const createMutation = useCreateCountry();
  const updateMutation = useUpdateCountry();

  const form = useForm<CountrySchemaType>({
    resolver: zodResolver(CountrySchema),
    defaultValues: EMPTY,
    mode: 'onTouched',
  });

  useEffect(() => {
    if (!open) return;
    form.reset(
      country
        ? { code: country.code, name: country.name, is_active: country.is_active }
        : EMPTY,
    );
  }, [open, country, form]);

  const isSaving = createMutation.isPending || updateMutation.isPending;

  const onSubmit = async (values: CountrySchemaType) => {
    const payload = {
      code: values.code.trim().toUpperCase(),
      name: values.name.trim(),
      is_active: values.is_active,
    };
    try {
      if (isEditMode && country) {
        await updateMutation.mutateAsync({ id: country.id, data: payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onOpenChange(false);
    } catch {
      // The mutation hooks surface the extracted error as a toast.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Edit country' : 'Add country'}</DialogTitle>
          <DialogDescription className="sr-only">
            {isEditMode
              ? 'Change this country\'s code or name.'
              : 'Add a country a supplier can be set to.'}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Code</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="MY"
                      maxLength={2}
                      {...field}
                      disabled={isSaving}
                      className="uppercase"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Malaysia" {...field} disabled={isSaving} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between gap-4 rounded-md border p-3">
                  <FormLabel>Active</FormLabel>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      disabled={isSaving}
                    />
                  </FormControl>
                </FormItem>
              )}
            />
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSaving}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving ? <LoaderCircleIcon className="animate-spin" /> : <Save />}
                {isEditMode ? 'Save changes' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
