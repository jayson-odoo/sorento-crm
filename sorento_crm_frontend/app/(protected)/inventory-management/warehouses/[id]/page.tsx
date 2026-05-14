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
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { useWarehouse, useDeleteWarehouse } from '../hooks/useWarehouses';
import { formatDate } from '@/lib/helpers';

export default function WarehouseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: warehouse, isLoading } = useWarehouse(id);
  const deleteMutation = useDeleteWarehouse();

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to deactivate this warehouse?')) {
      return;
    }
    try {
      await deleteMutation.mutateAsync(id);
      router.push('/inventory-management/warehouses');
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
              <ToolbarTitle>Warehouse</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Inventory Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/inventory-management/warehouses">
                      Warehouses
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/inventory-management/warehouses">
                  <MoveLeft /> Back to warehouses
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

  if (!warehouse) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Warehouse</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Inventory Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/inventory-management/warehouses">
                      Warehouses
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/inventory-management/warehouses">
                  <MoveLeft /> Back to warehouses
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Warehouse not found</p>
            <Button
              variant="outline"
              onClick={() => router.push('/inventory-management/warehouses')}
              className="mt-4"
            >
              <MoveLeft className="size-4" />
              Back to Warehouses
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
            <ToolbarTitle>Warehouse</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Inventory Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/inventory-management/warehouses">
                    Warehouses
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href="/inventory-management/warehouses">
                <MoveLeft /> Back to warehouses
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
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold">{warehouse.warehouse_name || warehouse.warehouse_code}</h1>
                <Badge
                  variant={warehouse.is_active ? 'success' : 'secondary'}
                  appearance="ghost"
                >
                  {warehouse.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                System Location: {warehouse.warehouse_code}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => router.push(`/inventory-management/warehouses/${id}/edit`)}
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
                  <p className="text-sm text-muted-foreground">System Location</p>
                  <p className="font-medium">{warehouse.warehouse_code}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">System Location Description</p>
                  <p className="font-medium">{warehouse.warehouse_name || '-'}</p>
                </div>
                {warehouse.location && (
                  <div>
                    <p className="text-sm text-muted-foreground">Warehouse</p>
                    <p className="font-medium">{warehouse.location}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge
                    variant={warehouse.is_active ? 'success' : 'secondary'}
                    appearance="ghost"
                  >
                    {warehouse.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-sm">
                    {formatDate(new Date(warehouse.created_at))}
                  </p>
                </div>
                {warehouse.updated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Last Updated</p>
                    <p className="font-medium text-sm">
                      {formatDate(new Date(warehouse.updated_at))}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </Container>
    </>
  );
}
