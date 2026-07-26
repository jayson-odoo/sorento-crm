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
import {
  useRequestQuotation,
  useAnnotateRequestQuotation,
} from '../hooks/useRequestQuotations';
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
          <ToolbarTitle>Request Quotation</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Procurement</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/procurement-management/request-quotations">
                  Request Quotations
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/procurement-management/request-quotations">
              <MoveLeft /> Back to Request Quotations
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
  return new Intl.NumberFormat('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

export default function RequestQuotationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: rq, isLoading } = useRequestQuotation(id);
  const annotate = useAnnotateRequestQuotation();

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

  if (!rq) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Request quotation not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/procurement-management/request-quotations">
                <MoveLeft className="size-4" /> Back to Request Quotations
              </Link>
            </Button>
          </div>
        </Container>
      </>
    );
  }

  const supplierLabel = rq.supplier_name || rq.supplier_code || rq.creditor_code || '—';

  return (
    <>
      <Header />
      <Container>
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold break-words">{rq.rq_number}</h1>
              </div>
              <p className="text-sm text-muted-foreground">
                {supplierLabel}
                {rq.doc_date ? ` • Doc date: ${formatDate(new Date(rq.doc_date))}` : ''}
              </p>
            </div>
            <AutoCountSourceBadge source={rq.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Request quotation details — always rendered */}
            <Card>
              <CardHeader>
                <CardTitle>Request quotation details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="RQ Number" value={rq.rq_number} />
                <Field label="Doc No" value={rq.source_doc_no || '-'} />
                <Field label="Supplier Code" value={rq.supplier_code || '-'} />
                <Field label="Supplier Name" value={rq.supplier_name || '-'} />
                <Field
                  label="Doc Date"
                  value={rq.doc_date ? formatDate(new Date(rq.doc_date)) : '-'}
                />
                <Field label="Purchase Agent" value={rq.purchase_agent || '-'} />
                <Field label="Created" value={formatDate(new Date(rq.created_at))} />
              </CardContent>
            </Card>

            <MirrorAnnotationCard
              value={{ internal_note: rq.internal_note, follow_up: rq.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>

          {/* Request items — always rendered, with an explicit empty state */}
          <Card>
            <CardHeader>
              <CardTitle>Request items</CardTitle>
            </CardHeader>
            <CardContent>
              {rq.lines && rq.lines.length > 0 ? (
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
                        <th className="py-2 pr-4 font-medium text-right">Sub Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rq.lines.map((line) => (
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
                          <td className="py-2 pr-4 text-right">{fmtMoney(line.sub_total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">
                  This request quotation has no items.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </Container>
    </>
  );
}
