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
import { useTaxCode, useAnnotateTaxCode } from '../hooks/useTaxCodes';
import { formatDate } from '@/lib/helpers';

const SUPPLY_LABEL: Record<string, string> = { S: 'Supply', P: 'Purchase' };

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
          <ToolbarTitle>Tax Code</ToolbarTitle>
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
                <BreadcrumbLink href="/master-data-management/tax-codes">
                  Tax Codes
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/master-data-management/tax-codes">
              <MoveLeft /> Back to Tax Codes
            </Link>
          </Button>
        </ToolbarActions>
      </Toolbar>
    </Container>
  );
}

export default function TaxCodeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: tax, isLoading } = useTaxCode(id);
  const annotate = useAnnotateTaxCode();

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

  if (!tax) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Tax code not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/master-data-management/tax-codes">
                <MoveLeft className="size-4" /> Back to Tax Codes
              </Link>
            </Button>
          </div>
        </Container>
      </>
    );
  }

  const rate =
    tax.tax_rate === null || tax.tax_rate === undefined || tax.tax_rate === ''
      ? '-'
      : `${Number(tax.tax_rate)}%`;

  return (
    <>
      <Header />
      <Container>
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <h1 className="text-2xl font-bold break-words">{tax.tax_code}</h1>
              <p className="text-sm text-muted-foreground">Tax code</p>
            </div>
            <AutoCountSourceBadge source={tax.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Tax Code" value={tax.tax_code} />
                <Field
                  label="Type"
                  value={
                    tax.supply_purchase
                      ? SUPPLY_LABEL[tax.supply_purchase] || tax.supply_purchase
                      : '-'
                  }
                />
                <Field label="Rate" value={rate} />
                <Field
                  label="Status"
                  value={
                    <Badge
                      variant={tax.is_active ? 'success' : 'secondary'}
                      appearance="ghost"
                    >
                      <BadgeDot />
                      {tax.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  }
                />
                <Field label="Created" value={formatDate(new Date(tax.created_at))} />
                {tax.updated_at && (
                  <Field label="Last Updated" value={formatDate(new Date(tax.updated_at))} />
                )}
              </CardContent>
            </Card>

            <MirrorAnnotationCard
              value={{ internal_note: tax.internal_note, follow_up: tax.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>
        </div>
      </Container>
    </>
  );
}
