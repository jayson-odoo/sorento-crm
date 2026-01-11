'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft, Edit, Trash2 } from 'lucide-react';
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
import { useUOM, useDeleteUOM } from '../hooks/useUOM';
import { formatDate } from '@/lib/helpers';

export default function UOMDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: uom, isLoading } = useUOM(id);
  const deleteMutation = useDeleteUOM();

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this UOM?')) {
      return;
    }
    try {
      await deleteMutation.mutateAsync(id);
      router.push('/master-data-management/units-of-measure');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  if (isLoading) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Unit of Measure</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Master Data Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/master-data-management/units-of-measure">
                      Units of Measure
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/master-data-management/units-of-measure">
                  <MoveLeft /> Back to UOMs
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!uom) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Unit of Measure</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Master Data Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/master-data-management/units-of-measure">
                      Units of Measure
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/master-data-management/units-of-measure">
                  <MoveLeft /> Back to UOMs
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">UOM not found</p>
            <Button
              variant="outline"
              onClick={() => router.push('/master-data-management/units-of-measure')}
              className="mt-4"
            >
              <MoveLeft className="size-4" />
              Back to Units of Measure
            </Button>
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Unit of Measure</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Master Data Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/master-data-management/units-of-measure">
                    Units of Measure
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href="/master-data-management/units-of-measure">
                <MoveLeft /> Back to UOMs
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h1 className="text-2xl font-bold">{uom.uom_name}</h1>
              <p className="text-sm text-muted-foreground">
                UOM Code: {uom.uom_code}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => router.push(`/master-data-management/units-of-measure/${id}/edit`)}
              >
                <Edit className="size-4" />
                Edit
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
              >
                <Trash2 className="size-4" />
                Delete
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">UOM Code</p>
                  <p className="font-medium">{uom.uom_code}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">UOM Name</p>
                  <p className="font-medium">{uom.uom_name}</p>
                </div>
                {uom.base_uom && (
                  <div>
                    <p className="text-sm text-muted-foreground">Base UOM</p>
                    <p className="font-medium">
                      {uom.base_uom.uom_name} ({uom.base_uom.uom_code})
                    </p>
                  </div>
                )}
                {uom.conversion_factor && (
                  <div>
                    <p className="text-sm text-muted-foreground">Conversion Factor</p>
                    <p className="font-medium">{uom.conversion_factor}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-sm">
                    {formatDate(new Date(uom.created_at))}
                  </p>
                </div>
                {uom.updated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Last Updated</p>
                    <p className="font-medium text-sm">
                      {formatDate(new Date(uom.updated_at))}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>

            {uom.description && (
              <Card>
                <CardHeader>
                  <CardTitle>Description</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap">{uom.description}</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </Container>
    </>
  );
}
