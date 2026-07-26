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
import { usePaymentMethod, useAnnotatePaymentMethod } from '../hooks/usePaymentMethods';
import { formatDate } from '@/lib/helpers';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="font-medium">{value ?? '-'}</p>
    </div>
  );
}

function Header() {
  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Payment Method</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Master Data</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/master-data-management/payment-methods">
                  Payment Methods
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/master-data-management/payment-methods">
              <MoveLeft /> Back to Payment Methods
            </Link>
          </Button>
        </ToolbarActions>
      </Toolbar>
    </Container>
  );
}

export default function PaymentMethodDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: method, isLoading } = usePaymentMethod(id);
  const annotate = useAnnotatePaymentMethod();

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

  if (!method) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Payment method not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/master-data-management/payment-methods">
                <MoveLeft className="size-4" /> Back to Payment Methods
              </Link>
            </Button>
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Header />
      <Container>
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <h1 className="text-2xl font-bold break-words">{method.payment_method}</h1>
              <p className="text-sm text-muted-foreground">Payment method</p>
            </div>
            <AutoCountSourceBadge source={method.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Basic information — always rendered */}
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Payment Method" value={method.payment_method} />
                <Field label="Description" value={method.description || '-'} />
                <Field label="Bank Account" value={method.bank_account || '-'} />
                <Field label="Journal Type" value={method.journal_type || '-'} />
                <Field
                  label="Status"
                  value={
                    <Badge
                      variant={method.is_active ? 'success' : 'secondary'}
                      appearance="ghost"
                    >
                      <BadgeDot />
                      {method.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  }
                />
                <Field label="Created" value={formatDate(new Date(method.created_at))} />
                {method.updated_at && (
                  <Field label="Last Updated" value={formatDate(new Date(method.updated_at))} />
                )}
              </CardContent>
            </Card>

            {/* Annotation — the only editable surface */}
            <MirrorAnnotationCard
              value={{ internal_note: method.internal_note, follow_up: method.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>
        </div>
      </Container>
    </>
  );
}
