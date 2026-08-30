'use client';

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { LoaderCircleIcon } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
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
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useUpdateNumberingRule } from '../hooks/useNumberingRules';
import type { DocumentNumberingRule } from '../types/numberingRule.types';
import { DOC_TYPE_LABELS, RESET_POLICY_OPTIONS } from '../types/numberingRule.types';

interface FormValues {
  enabled: boolean;
  prefix_template: string;
  number_digits: number;
  next_value: number;
  start_value: number;
  reset_policy: string;
}

interface NumberingRuleEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rule: DocumentNumberingRule | null;
}

export default function NumberingRuleEditDialog({
  open,
  onOpenChange,
  rule,
}: NumberingRuleEditDialogProps) {
  const updateMutation = useUpdateNumberingRule();

  const form = useForm<FormValues>({
    defaultValues: {
      enabled: true,
      prefix_template: '',
      number_digits: 4,
      next_value: 1,
      start_value: 1,
      reset_policy: 'none',
    },
  });

  useEffect(() => {
    if (rule) {
      form.reset({
        enabled: rule.enabled,
        prefix_template: rule.prefix_template ?? '',
        number_digits: rule.number_digits,
        next_value: rule.next_value,
        start_value: rule.start_value,
        reset_policy: rule.reset_policy,
      });
    }
  }, [rule, form]);

  const onSubmit = (data: FormValues) => {
    if (!rule) return;
    updateMutation.mutate(
      {
        docType: rule.doc_type,
        data: {
          enabled: data.enabled,
          prefix_template: data.prefix_template || null,
          number_digits: data.number_digits,
          next_value: data.next_value,
          start_value: data.start_value,
          reset_policy: data.reset_policy,
        },
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  if (!rule) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Edit: {DOC_TYPE_LABELS[rule.doc_type] ?? rule.doc_type}
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="prefix_template"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Prefix (use {'{year}'}, {'{yy}'}, {'{month}'}, {'{day}'})</FormLabel>
                  <FormControl>
                    <Input placeholder="PR-{year}- or PSSF{yy}-" {...field} />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    {'{year}'} = 4-digit (2026), {'{yy}'} = 2-digit (26)
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="number_digits"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Number digits (padding)</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 1)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="next_value"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Next running number</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 0)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="start_value"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Start value (after reset)</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 0)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="reset_policy"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reset policy</FormLabel>
                  <FormControl>
                    <SearchableSelect
                      value={field.value}
                      onChange={field.onChange}
                      options={RESET_POLICY_OPTIONS.map((opt) => ({
                        value: opt.value,
                        label: opt.label,
                      }))}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="enabled"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormLabel className="!mt-0">Enabled</FormLabel>
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending && <LoaderCircleIcon className="mr-2 size-4 animate-spin" />}
                Save numbering rule
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
