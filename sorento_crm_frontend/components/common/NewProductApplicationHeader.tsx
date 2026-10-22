'use client';

/**
 * The header of a new product application (NEW-PRODUCT-APP v5): Stock Inquiry's label:value table
 * rows (`ProductInquiryFormLayout`), titled NEW PRODUCT APPLICATION, shared by the staff form and
 * detail and the portal form so they cannot drift. `readOnly` shows plain values in place of the
 * inputs. LEADTIME is purchasing's feedback: read-only to everyone else, with the waiting line
 * until it is filled, and editable in place (with Save feedback) when `feedback.editable`.
 */

import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  InquiryFormTableRow,
  InquiryReadValue,
  ProductInquiryFormLayout,
} from '@/app/(protected)/procurement-management/stock-inquiries/components/ProductInquiryFormLayout';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { FormState } from '@/lib/new-product-application-form';

export interface NewProductApplicationHeaderProps {
  value: FormState;
  onChange: (next: FormState) => void;
  applicationNo?: string | null;
  createdAt?: string | null;
  /** Omitted on the portal, which has no salesperson row. */
  salesPerson?: string | null;
  readOnly?: boolean;
  stockInquiryField: ReactNode;
  customerField: ReactNode;
  feedback?: { editable: boolean; onSave?: () => void; saving?: boolean };
}

export function NewProductApplicationHeader({
  value,
  onChange,
  applicationNo,
  createdAt,
  salesPerson,
  readOnly,
  stockInquiryField,
  customerField,
  feedback,
}: NewProductApplicationHeaderProps) {
  const patch = (next: Partial<FormState>) => onChange({ ...value, ...next });
  const editableFeedback = Boolean(feedback?.editable);

  return (
    <ProductInquiryFormLayout title="NEW PRODUCT APPLICATION">
      <InquiryFormTableRow label="REFF:">
        <InquiryReadValue>{applicationNo}</InquiryReadValue>
      </InquiryFormTableRow>
      <InquiryFormTableRow label="DATE:">
        <InquiryReadValue>
          {formatDateInMalaysia(createdAt ?? new Date())}
        </InquiryReadValue>
      </InquiryFormTableRow>
      {salesPerson !== undefined && (
        <InquiryFormTableRow label="SALES PERSON:">
          <InquiryReadValue>{salesPerson}</InquiryReadValue>
        </InquiryFormTableRow>
      )}
      <InquiryFormTableRow label="STOCK INQUIRY:">
        {stockInquiryField}
      </InquiryFormTableRow>
      <InquiryFormTableRow label="CUSTOMER:">
        {customerField}
      </InquiryFormTableRow>
      <InquiryFormTableRow label="PROJECT:">
        {readOnly ? (
          <InquiryReadValue>{value.project_name}</InquiryReadValue>
        ) : (
          <Input
            aria-label="Project"
            value={value.project_name}
            onChange={(e) => patch({ project_name: e.target.value })}
          />
        )}
      </InquiryFormTableRow>
      <InquiryFormTableRow label="TARGET DELIVERY:">
        {readOnly ? (
          <InquiryReadValue>
            {value.needed_by ? formatDateInMalaysia(value.needed_by) : ''}
          </InquiryReadValue>
        ) : (
          <Input
            aria-label="Target delivery"
            type="date"
            value={value.needed_by}
            onChange={(e) => patch({ needed_by: e.target.value })}
          />
        )}
      </InquiryFormTableRow>
      <InquiryFormTableRow label="REMARK:">
        {readOnly ? (
          <InquiryReadValue>{value.remark}</InquiryReadValue>
        ) : (
          <Textarea
            aria-label="Remark"
            rows={3}
            value={value.remark}
            onChange={(e) => patch({ remark: e.target.value })}
          />
        )}
      </InquiryFormTableRow>
      <InquiryFormTableRow label="LEADTIME:">
        {editableFeedback ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              aria-label="Lead time"
              value={value.lead_time}
              onChange={(e) => patch({ lead_time: e.target.value })}
            />
            <Button
              type="button"
              size="sm"
              className="shrink-0"
              disabled={feedback?.saving}
              onClick={() => feedback?.onSave?.()}
            >
              Save feedback
            </Button>
          </div>
        ) : value.lead_time.trim() ? (
          <InquiryReadValue>{value.lead_time}</InquiryReadValue>
        ) : (
          <p className="text-muted-foreground">
            Purchasing fills this after approval.
          </p>
        )}
      </InquiryFormTableRow>
    </ProductInquiryFormLayout>
  );
}
