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
import { Textarea } from '@/components/ui/textarea';
import { useCreateItemClass } from '../hooks/useItemClasses';
import { ItemClassSchema, type ItemClassSchemaType } from '../forms/item-class-schema';

interface ItemClassFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const EMPTY: ItemClassSchemaType = {
  item_class_code: '',
  item_class_name: '',
  description: '',
  is_active: true,
};

/** Create only: an existing class is edited in place on its record page. */
export default function ItemClassFormDialog({ open, onOpenChange }: ItemClassFormDialogProps) {
  const createMutation = useCreateItemClass();

  const form = useForm<ItemClassSchemaType>({
    resolver: zodResolver(ItemClassSchema),
    defaultValues: EMPTY,
    mode: 'onTouched',
  });

  useEffect(() => {
    if (open) form.reset(EMPTY);
  }, [open, form]);

  const isSaving = createMutation.isPending;

  const onSubmit = async (values: ItemClassSchemaType) => {
    try {
      await createMutation.mutateAsync({
        item_class_code: values.item_class_code.trim(),
        item_class_name: values.item_class_name.trim(),
        description: values.description.trim() || null,
        is_active: values.is_active,
      });
      onOpenChange(false);
    } catch {
      // The mutation hook surfaces the extracted error as a toast.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add item class</DialogTitle>
          <DialogDescription className="sr-only">Add an item class.</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="item_class_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Code</FormLabel>
                  <FormControl>
                    <Input {...field} maxLength={50} disabled={isSaving} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="item_class_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} maxLength={150} disabled={isSaving} />
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
                    <Textarea rows={3} {...field} disabled={isSaving} />
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
                Create
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
