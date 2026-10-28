'use client';

import type { ReactNode } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import {
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import { Textarea } from '@/components/ui/textarea';
import { InquiryFormTableRow } from './ProductInquiryFormLayout';
import { PRODUCT_INQUIRY_REMARK_HINT } from '../productInquiryFormConstants';
import type { StockInquirySchemaType } from '../forms/stock-inquiry-schema';

/**
 * The inquiry's own fields, in form order, shared by the staff form and a salesperson's own
 * form (PORTAL-P4-REQUESTS) so the two cannot drift. The Sales person picker is the caller's:
 * staff and a salesperson read different eligible sets.
 */
export default function StockInquiryFieldRows({
  form,
  salesperson,
  readOnly = false,
}: {
  form: UseFormReturn<StockInquirySchemaType>;
  salesperson: ReactNode;
  readOnly?: boolean;
}) {
  return (
    <>
      <InquiryFormTableRow label="Sales person">{salesperson}</InquiryFormTableRow>

      <InquiryFormTableRow label="Product code">
        <FormField
          control={form.control}
          name="product_code"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <Input
                  className="h-9"
                  placeholder="Code"
                  {...field}
                  disabled={readOnly}
                  value={field.value || ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Item description" labelClassName="items-start pt-3">
        <FormField
          control={form.control}
          name="item_description"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <Textarea
                  placeholder="Description"
                  {...field}
                  disabled={readOnly}
                  value={field.value || ''}
                  rows={3}
                  className="min-h-[4.5rem] resize-y"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Project customer">
        <FormField
          control={form.control}
          name="project_customer"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <Input
                  className="h-9"
                  placeholder="Customer / site"
                  {...field}
                  disabled={readOnly}
                  value={field.value || ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Project name">
        <FormField
          control={form.control}
          name="project_name"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <Input
                  className="h-9"
                  placeholder="Project name"
                  {...field}
                  disabled={readOnly}
                  value={field.value || ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Qty">
        <FormField
          control={form.control}
          name="quantity"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <NumberInput
                  className="h-9"
                  min={0}
                  step="any"
                  inputMode="decimal"
                  placeholder="Quantity"
                  {...field}
                  disabled={readOnly}
                  value={field.value ?? ''}
                  onChange={(e) => field.onChange(e.target.value)}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Delivery date">
        <FormField
          control={form.control}
          name="delivery_date"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <Input
                  className="h-9"
                  placeholder="e.g. MOCK UP - MAY 2026, BALANCE BY AUG/SEPT 2026"
                  {...field}
                  disabled={readOnly}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Remark" labelClassName="items-start pt-3">
        <div className="space-y-2">
          <FormField
            control={form.control}
            name="remark"
            render={({ field }) => (
              <FormItem className="space-y-1">
                <FormControl>
                  <Textarea
                    placeholder="Remarks"
                    {...field}
                    disabled={readOnly}
                    value={field.value ?? ''}
                    rows={6}
                    className="min-h-[8rem] resize-y font-normal"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <p className="text-xs text-muted-foreground leading-snug">
            {PRODUCT_INQUIRY_REMARK_HINT}
          </p>
        </div>
      </InquiryFormTableRow>

      <InquiryFormTableRow label="Additional remark" labelClassName="items-start pt-3">
        <FormField
          control={form.control}
          name="additional_remark"
          render={({ field }) => (
            <FormItem className="space-y-1">
              <FormControl>
                <Textarea
                  placeholder="Additional notes"
                  {...field}
                  disabled={readOnly}
                  value={field.value || ''}
                  rows={4}
                  className="min-h-[6rem] resize-y"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </InquiryFormTableRow>
    </>
  );
}
