'use client';

import { use } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { AutoCountSourceBadge } from '@/components/common/AutoCountSourceBadge';
import { MirrorAnnotationCard } from '@/components/common/MirrorAnnotationCard';
import { useQuotation, useAnnotateQuotation } from '../hooks/useQuotations';
import { formatDate } from '@/lib/helpers';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="font-medium break-words">{value ?? '-'}</p>
    </div>
  );
}

function Header() {
  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Quotation</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Order Management</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/order-management/quotations">Quotations</BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/order-management/quotations">
              <MoveLeft /> Back to Quotations
            </Link>
          </Button>
        </ToolbarActions>
      </Toolbar>
    </Container>
  );
}

function fmtNum(v: string | number | null): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : String(n);
}

function fmtMoney(v: string | number | null): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return new Intl.NumberFormat('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

export default function QuotationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: quote, isLoading } = useQuotation(id);
  const annotate = useAnnotateQuotation();

  if (isLoading) {
    return (
      <>
        <Header />
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!quote) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Quotation not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/order-management/quotations">
                <MoveLeft className="size-4" /> Back to Quotations
              </Link>
            </Button>
          </div>
        </Container>
      </>
    );
  }

  const deliverAddress = [
    quote.deliver_addr1,
    quote.deliver_addr2,
    quote.deliver_addr3,
    quote.deliver_addr4,
  ]
    .map((line) => (line || '').trim())
    .filter(Boolean);

  return (
    <>
      <Header />
      <Container>
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold break-words">{quote.quote_number}</h1>
                {quote.is_cancelled && (
                  <Badge variant="destructive" appearance="ghost">
                    <BadgeDot />
                    Cancelled
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {quote.debtor_name || quote.debtor_code || '—'}
                {quote.doc_date ? ` • Doc date: ${formatDate(new Date(quote.doc_date))}` : ''}
              </p>
            </div>
            <AutoCountSourceBadge source={quote.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Quotation details — always rendered */}
            <Card>
              <CardHeader>
                <CardTitle>Quotation details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Quote Number" value={quote.quote_number} />
                <Field label="Doc No" value={quote.source_doc_no || '-'} />
                <Field
                  label="Doc Date"
                  value={quote.doc_date ? formatDate(new Date(quote.doc_date)) : '-'}
                />
                <Field label="Debtor Code" value={quote.debtor_code || '-'} />
                <Field label="Debtor Name" value={quote.debtor_name || '-'} />
                <Field label="Attention" value={quote.attention || '-'} />
                <Field label="Branch Code" value={quote.branch_code || '-'} />
                <Field label="Terms" value={quote.terms || '-'} />
                <Field label="Sales Agent" value={quote.sales_agent || '-'} />
                <Field label="Cancelled" value={quote.is_cancelled ? 'Yes' : 'No'} />
                <Field label="Created" value={formatDate(new Date(quote.created_at))} />
              </CardContent>
            </Card>

            <MirrorAnnotationCard
              value={{ internal_note: quote.internal_note, follow_up: quote.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>

          {/* Delivery address — always rendered, with an explicit empty state */}
          <Card>
            <CardHeader>
              <CardTitle>Delivery address</CardTitle>
            </CardHeader>
            <CardContent>
              {deliverAddress.length > 0 ? (
                <div className="space-y-0.5">
                  {deliverAddress.map((line, i) => (
                    <p key={i} className="font-medium break-words">
                      {line}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">No delivery address on this quotation.</p>
              )}
            </CardContent>
          </Card>

          {/* Quotation lines — always rendered, with an explicit empty state */}
          <Card>
            <CardHeader>
              <CardTitle>Quotation items</CardTitle>
            </CardHeader>
            <CardContent>
              {quote.lines && quote.lines.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground text-left">
                        <th className="py-2 pr-4 font-medium">#</th>
                        <th className="py-2 pr-4 font-medium">Product</th>
                        <th className="py-2 pr-4 font-medium">UOM</th>
                        <th className="py-2 pr-4 font-medium">Location</th>
                        <th className="py-2 pr-4 font-medium text-right">Qty</th>
                        <th className="py-2 pr-4 font-medium text-right">Unit Price</th>
                        <th className="py-2 pr-4 font-medium text-right">Discount</th>
                        <th className="py-2 pr-4 font-medium text-right">Sub Total</th>
                        <th className="py-2 pr-4 font-medium">Tax</th>
                        <th className="py-2 pr-4 font-medium text-right">Tax Amt</th>
                        <th className="py-2 pr-4 font-medium">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {quote.lines.map((line) => (
                        <tr key={line.id} className="border-b last:border-0 align-top">
                          <td className="py-2 pr-4">{line.line_sequence}</td>
                          <td className="py-2 pr-4">
                            <span className="font-medium">{line.product_code || '-'}</span>
                            {line.product_name && (
                              <span
                                className="block text-muted-foreground truncate max-w-xs"
                                title={line.product_name}
                              >
                                {line.product_name}
                              </span>
                            )}
                          </td>
                          <td className="py-2 pr-4">{line.uom || '-'}</td>
                          <td className="py-2 pr-4">{line.location || '-'}</td>
                          <td className="py-2 pr-4 text-right">{fmtNum(line.qty)}</td>
                          <td className="py-2 pr-4 text-right">{fmtMoney(line.unit_price)}</td>
                          <td className="py-2 pr-4 text-right">{fmtMoney(line.discount_amt)}</td>
                          <td className="py-2 pr-4 text-right">{fmtMoney(line.sub_total)}</td>
                          <td className="py-2 pr-4">
                            {line.tax_code || '-'}
                            {line.tax_rate !== null && line.tax_rate !== undefined && line.tax_rate !== ''
                              ? ` (${fmtNum(line.tax_rate)}%)`
                              : ''}
                          </td>
                          <td className="py-2 pr-4 text-right">{fmtMoney(line.tax)}</td>
                          <td className="py-2 pr-4">
                            <span
                              className="block truncate max-w-xs"
                              title={line.description || ''}
                            >
                              {line.description || '-'}
                            </span>
                            {line.further_description && (
                              <span
                                className="block text-muted-foreground truncate max-w-xs"
                                title={line.further_description}
                              >
                                {line.further_description}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">This quotation has no items.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </Container>
    </>
  );
}
