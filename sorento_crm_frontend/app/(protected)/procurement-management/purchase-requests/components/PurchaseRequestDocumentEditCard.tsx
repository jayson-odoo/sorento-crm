'use client';

import type { UseFormReturn, FieldArrayWithId } from 'react-hook-form';
import { formatDate, formatCurrency } from '@/lib/helpers';
import { useCurrencyFormat } from '@/hooks/useCurrencyFormat';
import { Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  FormControl,
  FormField,
  FormItem,
  FormMessage,
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
import LookupBoundField from '@/components/common/LookupBoundField';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { PurchaseRequestSchemaType } from '../forms/purchase-request-schema';
import type { PurchaseRequest } from '../types/purchaseRequest.types';
import { PurchaseRequestSignoffFooter } from './PurchaseRequestSignoffFooter';
import { purchaseRequestNumberFieldLabel } from '../lib/purchase-request-field-labels';

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

function DocField({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

type Props = {
  form: UseFormReturn<PurchaseRequestSchemaType>;
  request: PurchaseRequest;
  isSponsorship: boolean;
  showTypeSelect: boolean;
  fields: FieldArrayWithId<PurchaseRequestSchemaType, 'products', 'id'>[];
  append: (v: {
    item_code: null;
    quantity: null;
    remark: null;
    unit_price: null;
    total: null;
  }) => void;
  remove: (index: number) => void;
  sponsorshipLineGrandTotal: number;
};

export function PurchaseRequestDocumentEditCard({
  form,
  request,
  isSponsorship,
  showTypeSelect,
  fields,
  append,
  remove,
  sponsorshipLineGrandTotal,
}: Props) {
  const { control } = form;
  const currencyFormat = useCurrencyFormat();
  const typeLabel =
    REQUEST_TYPE_LABELS[request.request_type ?? ''] ?? request.request_type ?? 'Request';

  return (
    <div className="max-w-5xl mx-auto w-full">
      <Card className="border-2 shadow-sm">
        <CardContent className="pt-6 pb-8 px-5 sm:px-10">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{typeLabel}</Badge>
              <Badge
                variant={
                  request.approval_status === 'approved'
                    ? 'primary'
                    : request.approval_status === 'rejected'
                      ? 'destructive'
                      : 'secondary'
                }
              >
                {request.approval_status === 'pending'
                  ? 'Pending approval'
                  : request.approval_status === 'approved'
                    ? 'Approved'
                    : request.approval_status === 'rejected'
                      ? 'Rejected'
                      : (request.status ?? '').toLowerCase() === 'submitted'
                        ? 'Submitted'
                        : (request.status ?? '').toLowerCase() === 'draft'
                          ? 'Draft'
                          : (request.approval_status || request.status || 'Draft')}
              </Badge>
            </div>
          </div>

          <h2 className="text-center text-xl font-semibold tracking-tight border-b border-border pb-4 mb-6">
            {isSponsorship ? 'Project Sales Sponsorship Form' : 'Purchase Request'}
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-5">
            {showTypeSelect && (
              <DocField label="Type" className="sm:col-span-2">
                <FormField
                  control={control}
                  name="request_type"
                  render={({ field }) => (
                    <FormItem>
                      <Select onValueChange={field.onChange} value={field.value ?? ''} disabled>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="purchase_request">Purchase Request</SelectItem>
                          <SelectItem value="sponsorship_form">Sponsorship Form</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </DocField>
            )}

            <DocField label={purchaseRequestNumberFieldLabel(request.request_type)}>
              <FormField
                control={control}
                name="request_number"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input
                        placeholder="e.g. PR26-0303"
                        {...field}
                        value={field.value ?? ''}
                        readOnly
                        className="font-medium tabular-nums"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </DocField>

            <DocField label="Submitted date">
              {/* Auto-stamped on submit; read-only. */}
              <p className="font-medium py-2">
                {request.submitted_at ? formatDate(new Date(request.submitted_at)) : '—'}
              </p>
            </DocField>

            <DocField label="Customer Name" className="sm:col-span-2">
              <FormField
                control={control}
                name="customer_name"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input placeholder="Customer name" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </DocField>

            <DocField label="Project Title" className="sm:col-span-2">
              <FormField
                control={control}
                name="project_title"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input placeholder="Project title" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </DocField>

            {isSponsorship && (
              <DocField label="Delivery Address" className="sm:col-span-2">
                <FormField
                  control={control}
                  name="delivery_address"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea
                          placeholder="Delivery address"
                          rows={4}
                          className="resize-y min-h-[80px]"
                          {...field}
                          value={field.value ?? ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </DocField>
            )}

            {!isSponsorship && (
              <DocField label="Purpose" className="sm:col-span-2">
                <FormField
                  control={control}
                  name="purpose"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Input
                          placeholder="e.g. Showroom, Mock up, Others"
                          {...field}
                          value={field.value ?? ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </DocField>
            )}

            {isSponsorship && (
              <>
                <DocField label="Total Project Value" className="sm:col-span-2">
                  <FormField
                    control={control}
                    name="total_project_value"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input
                            type="number"
                            inputMode="decimal"
                            step="0.01"
                            placeholder="e.g. 1234.00"
                            {...field}
                            value={field.value ?? ''}
                            onChange={(e) =>
                              field.onChange(e.target.value === '' ? null : e.target.value)
                            }
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </DocField>
                <DocField label="Sponsor Subject" className="sm:col-span-2">
                  <FormField
                    control={control}
                    name="sponsor_subject"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <LookupBoundField
                            table="purchase_requests"
                            column="sponsor_subject"
                            value={field.value}
                            onChange={field.onChange}
                            placeholder="Select sponsor subject"
                            renderFallback={() => (
                              <Select
                                key={field.value || 'empty'}
                                onValueChange={field.onChange}
                                value={field.value || undefined}
                              >
                                <SelectTrigger>
                                  <SelectValue placeholder="Select sponsor subject" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="showroom">Showroom</SelectItem>
                                  <SelectItem value="mockup">Mockup</SelectItem>
                                  <SelectItem value="others">Others</SelectItem>
                                </SelectContent>
                              </Select>
                            )}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </DocField>
                {form.watch('sponsor_subject') === 'others' && (
                  <DocField label="Please specify" className="sm:col-span-2">
                    <FormField
                      control={control}
                      name="sponsor_subject_other"
                      render={({ field }) => (
                        <FormItem>
                          <FormControl>
                            <Input
                              placeholder="Specify the sponsor subject"
                              {...field}
                              value={field.value ?? ''}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </DocField>
                )}
              </>
            )}

            <DocField label={isSponsorship ? 'Date of Delivery' : 'Expected date of delivery'}>
              <FormField
                control={control}
                name="expected_delivery_date"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Input type="date" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </DocField>

            {!isSponsorship && (
              <DocField label="Expected date to receive PO">
                <div className="space-y-2">
                  <FormField
                    control={control}
                    name="expected_po_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input type="date" {...field} value={field.value ?? ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={control}
                    name="expected_po_date_text"
                    render={({ field }) => (
                      <FormItem>
                        <FormControl>
                          <Input
                            placeholder="Free text (e.g. PROPOSED STAGE)"
                            {...field}
                            value={field.value ?? ''}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </DocField>
            )}

            {(request.approver_email || request.approver_user_id) && !request.approved_at && (
              <div className="sm:col-span-2">
                <p className="text-sm text-muted-foreground">Approver</p>
                <p className="font-medium mt-1.5">
                  {request.approver_display_name
                    ? `${request.approver_display_name} (${request.approver_email})`
                    : request.approver_email}
                </p>
              </div>
            )}

            {request.respond_inbox_url && (
              <div className="sm:col-span-2">
                <p className="text-sm text-muted-foreground">Respond conversation</p>
                <a
                  href={request.respond_inbox_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline text-sm break-all font-medium mt-1.5 inline-block"
                >
                  {request.respond_inbox_url}
                </a>
              </div>
            )}
          </div>

          <div className="mt-8">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <p className="text-sm font-medium">Line items</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  append({
                    item_code: null,
                    quantity: null,
                    remark: null,
                    unit_price: null,
                    total: null,
                  })
                }
              >
                <Plus className="size-4" />
                Add row
              </Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  {isSponsorship ? (
                    <TableHead className="w-10">NO.</TableHead>
                  ) : (
                    <TableHead className="w-12">#</TableHead>
                  )}
                  <TableHead>Item Code</TableHead>
                  <TableHead className={isSponsorship ? 'w-24' : 'w-28'}>Qty</TableHead>
                  {isSponsorship && <TableHead>U/P</TableHead>}
                  {isSponsorship && <TableHead>Total</TableHead>}
                  <TableHead>Remark</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {fields.map((field, index) => (
                  <TableRow key={field.id}>
                    <TableCell className="text-muted-foreground text-sm align-middle">
                      {index + 1}
                    </TableCell>
                    <TableCell>
                      <FormField
                        control={control}
                        name={`products.${index}.item_code`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormControl>
                              <Input
                                placeholder="Item code"
                                {...f}
                                value={f.value ?? ''}
                                className="h-8"
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </TableCell>
                    <TableCell>
                      <FormField
                        control={control}
                        name={`products.${index}.quantity`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormControl>
                              <Input
                                type="number"
                                step="any"
                                placeholder="0"
                                {...f}
                                value={f.value ?? ''}
                                onChange={(e) => {
                                  const v = e.target.value ? parseFloat(e.target.value) : null;
                                  f.onChange(v);
                                  if (isSponsorship) {
                                    const up = form.getValues(`products.${index}.unit_price`);
                                    if (up != null && up !== '') {
                                      form.setValue(`products.${index}.total`, (v ?? 0) * Number(up));
                                    }
                                  }
                                }}
                                className="h-8 w-24"
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </TableCell>
                    {isSponsorship && (
                      <TableCell>
                        <FormField
                          control={control}
                          name={`products.${index}.unit_price`}
                          render={({ field: f }) => (
                            <FormItem>
                              <FormControl>
                                <Input
                                  type="number"
                                  step="any"
                                  placeholder="0"
                                  {...f}
                                  value={f.value ?? ''}
                                  onChange={(e) => {
                                    const v = e.target.value ? parseFloat(e.target.value) : null;
                                    f.onChange(v);
                                    const qty = form.getValues(`products.${index}.quantity`);
                                    if (qty != null && qty !== '') {
                                      form.setValue(`products.${index}.total`, (v ?? 0) * Number(qty));
                                    }
                                  }}
                                  className="h-8 w-24"
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </TableCell>
                    )}
                    {isSponsorship && (
                      <TableCell>
                        <FormField
                          control={control}
                          name={`products.${index}.total`}
                          render={({ field: f }) => (
                            <FormItem>
                              <FormControl>
                                <Input
                                  type="number"
                                  step="any"
                                  placeholder="0"
                                  {...f}
                                  value={f.value ?? ''}
                                  onChange={(e) => {
                                    const v = e.target.value ? parseFloat(e.target.value) : null;
                                    f.onChange(v);
                                  }}
                                  className="h-8 w-28"
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </TableCell>
                    )}
                    <TableCell>
                      <FormField
                        control={control}
                        name={`products.${index}.remark`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormControl>
                              <Input
                                placeholder="Remark"
                                {...f}
                                value={f.value ?? ''}
                                className="h-8"
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => remove(index)}
                        disabled={fields.length <= 1}
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {isSponsorship && (
              <div className="mt-3 flex justify-end border-t border-border pt-3">
                <p className="text-sm font-semibold tabular-nums">
                  Grand Total: {formatCurrency(sponsorshipLineGrandTotal, currencyFormat)}
                </p>
              </div>
            )}
          </div>

          <PurchaseRequestSignoffFooter
            request={request}
            renderRequestedColumn={() => (
              <>
                <div>
                  <p className="text-sm text-muted-foreground">Requested by</p>
                  <div className="mt-1.5">
                    <FormField
                      control={control}
                      name="requested_by"
                      render={({ field }) => (
                        <FormItem>
                          <FormControl>
                            <Input placeholder="Name" {...field} value={field.value ?? ''} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>
              </>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
