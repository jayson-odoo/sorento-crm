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
import { useItemPackage, useAnnotateItemPackage } from '../hooks/useItemPackages';
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
          <ToolbarTitle>Item Package</ToolbarTitle>
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
                <BreadcrumbLink href="/master-data-management/item-packages">
                  Item Packages
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/master-data-management/item-packages">
              <MoveLeft /> Back to Item Packages
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

export default function ItemPackageDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: pkg, isLoading } = useItemPackage(id);
  const annotate = useAnnotateItemPackage();

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

  if (!pkg) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Item package not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/master-data-management/item-packages">
                <MoveLeft className="size-4" /> Back to Item Packages
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
              <h1 className="text-2xl font-bold break-words">{pkg.package_code}</h1>
              <p className="text-sm text-muted-foreground">Item package</p>
            </div>
            <AutoCountSourceBadge source={pkg.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Package Code" value={pkg.package_code} />
                <Field label="Description" value={pkg.description || '-'} />
                <Field
                  label="Expiry Date"
                  value={pkg.expiry_date ? formatDate(new Date(pkg.expiry_date)) : '-'}
                />
                <Field label="Limited Qty" value={fmtNum(pkg.limited_qty)} />
                <Field label="Opening Qty" value={fmtNum(pkg.opening_qty)} />
                <Field label="User UOM" value={pkg.user_uom || '-'} />
                <Field label="Bar Code" value={pkg.bar_code || '-'} />
                <Field label="Further Description" value={pkg.further_description || '-'} />
                <Field
                  label="Status"
                  value={
                    <Badge variant={pkg.is_active ? 'success' : 'secondary'} appearance="ghost">
                      <BadgeDot />
                      {pkg.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  }
                />
                <Field label="Created" value={formatDate(new Date(pkg.created_at))} />
              </CardContent>
            </Card>

            <MirrorAnnotationCard
              value={{ internal_note: pkg.internal_note, follow_up: pkg.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>

          {/* Package lines — always rendered, with an explicit empty state */}
          <Card>
            <CardHeader>
              <CardTitle>Package items</CardTitle>
            </CardHeader>
            <CardContent>
              {pkg.lines && pkg.lines.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground text-left">
                        <th className="py-2 pr-4 font-medium">#</th>
                        <th className="py-2 pr-4 font-medium">Product</th>
                        <th className="py-2 pr-4 font-medium">UOM</th>
                        <th className="py-2 pr-4 font-medium text-right">Qty</th>
                        <th className="py-2 pr-4 font-medium text-right">Unit Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pkg.lines.map((line) => (
                        <tr key={line.id} className="border-b last:border-0">
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
                          <td className="py-2 pr-4 text-right">{fmtNum(line.qty)}</td>
                          <td className="py-2 pr-4 text-right">{fmtNum(line.unit_price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">This package has no items.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </Container>
    </>
  );
}
