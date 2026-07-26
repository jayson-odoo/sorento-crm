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
import { useTaxEntity, useAnnotateTaxEntity } from '../hooks/useTaxEntities';
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
          <ToolbarTitle>Tax Entity</ToolbarTitle>
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
                <BreadcrumbLink href="/master-data-management/tax-entities">
                  Tax Entities
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/master-data-management/tax-entities">
              <MoveLeft /> Back to Tax Entities
            </Link>
          </Button>
        </ToolbarActions>
      </Toolbar>
    </Container>
  );
}

export default function TaxEntityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: entity, isLoading } = useTaxEntity(id);
  const annotate = useAnnotateTaxEntity();

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

  if (!entity) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Tax entity not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/master-data-management/tax-entities">
                <MoveLeft className="size-4" /> Back to Tax Entities
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
              <h1 className="text-2xl font-bold break-words">
                {entity.name || entity.tax_entity_id}
              </h1>
              <p className="text-sm text-muted-foreground">Tax entity</p>
            </div>
            <AutoCountSourceBadge source={entity.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Basic information — always rendered */}
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Tax Entity ID" value={entity.tax_entity_id} />
                <Field label="Name" value={entity.name || '-'} />
                <Field label="TIN" value={entity.tin || '-'} />
                <Field label="Identity No" value={entity.identity_no || '-'} />
                <Field label="Tax Classification" value={entity.tax_classification ?? '-'} />
                <Field label="GST Reg No" value={entity.gst_register_no || '-'} />
                <Field label="SST Reg No" value={entity.sst_register_no || '-'} />
                <Field
                  label="Tourism Tax Reg No"
                  value={entity.tourism_tax_register_no || '-'}
                />
                <Field label="Trade Name" value={entity.trade_name || '-'} />
                <Field label="Business Activity" value={entity.business_activity_desc || '-'} />
                <Field label="MSIC Code" value={entity.msic_code || '-'} />
                <Field label="Address" value={entity.address || '-'} />
                <Field label="Post Code" value={entity.post_code || '-'} />
                <Field label="City" value={entity.city || '-'} />
                <Field label="State Code" value={entity.state_code || '-'} />
                <Field label="Country Code" value={entity.country_code || '-'} />
                <Field label="Phone" value={entity.phone || '-'} />
                <Field label="Email" value={entity.email_address || '-'} />
                <Field
                  label="Status"
                  value={
                    <Badge
                      variant={entity.is_active ? 'success' : 'secondary'}
                      appearance="ghost"
                    >
                      <BadgeDot />
                      {entity.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  }
                />
                <Field label="Created" value={formatDate(new Date(entity.created_at))} />
                {entity.updated_at && (
                  <Field label="Last Updated" value={formatDate(new Date(entity.updated_at))} />
                )}
              </CardContent>
            </Card>

            {/* Annotation — the only editable surface */}
            <MirrorAnnotationCard
              value={{ internal_note: entity.internal_note, follow_up: entity.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>
        </div>
      </Container>
    </>
  );
}
