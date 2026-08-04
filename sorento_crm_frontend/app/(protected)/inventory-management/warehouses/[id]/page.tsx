'use client';

import { use, useMemo, useState } from 'react';
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
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import RecordNavigation from '@/components/common/RecordNavigation';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { useWarehouse, useWarehouses } from '../hooks/useWarehouses';
import { deleteWarehouse } from '../services/warehouseService';
import { formatDate } from '@/lib/helpers';

/**
 * Read-only field row. Renders even when the record has no value for it.
 *
 * `className` carries the grid span, which must match the same field's span on the edit
 * form: matching DOM order is not enough, since a field spanning both columns in one view
 * and one column in the other lands in a different row and column between the two.
 */
function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={['min-w-0', className].filter(Boolean).join(' ')}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="font-medium break-words">{children}</div>
    </div>
  );
}

function WarehouseToolbar() {
  return (
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
  );
}

export default function WarehouseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: warehouse, isLoading } = useWarehouse(id);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Same list, same order, as the listing shows, so prev/next steps through it in order.
  const listParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 1000,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: warehouseList } = useWarehouses(listParams);
  const navigationItems = warehouseList?.data ?? [];

  if (isLoading) {
    return (
      <>
        <WarehouseToolbar />
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
        <WarehouseToolbar />
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

  const poolCode =
    warehouse.pool_warehouse_code && warehouse.pool_warehouse_id !== warehouse.id
      ? warehouse.pool_warehouse_code
      : null;

  return (
    <>
      <WarehouseToolbar />

      <Container>
        <div className="space-y-6">
          {/* Header. Read-only metadata lives here, never inside a tab body. */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold break-words">
                  {warehouse.warehouse_name || warehouse.warehouse_code}
                </h1>
                <Badge variant={warehouse.is_active ? 'success' : 'secondary'} appearance="ghost">
                  {warehouse.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                System Location: {warehouse.warehouse_code}
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>Created: {formatDate(new Date(warehouse.created_at))}</span>
                <span>
                  Last Updated:{' '}
                  {warehouse.updated_at ? formatDate(new Date(warehouse.updated_at)) : '-'}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <RecordNavigation
                basePath="/inventory-management/warehouses"
                currentId={id}
                items={navigationItems}
                totalCount={warehouseList?.pagination?.total}
                ariaLabel="warehouse"
              />
              <Button
                variant="outline"
                onClick={() => router.push(`/inventory-management/warehouses/${id}/edit`)}
              >
                <Edit className="size-4" />
                Edit
              </Button>
              <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
                <Trash2 className="size-4" />
                Delete
              </Button>
            </div>
          </div>

          {/* Same tab set, same field order, and the same grid spans as the edit view: a
              field that spans both columns there must span both here, or it lands in a
              different row and column between the two views. */}
          <Tabs defaultValue="basic">
            <TabsList>
              <TabsTrigger value="basic">Basic Information</TabsTrigger>
              <TabsTrigger value="planning">Planning</TabsTrigger>
            </TabsList>

            <TabsContent value="basic" className="mt-6">
              <Card>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-6">
                  <Field label="System Location">{warehouse.warehouse_code}</Field>
                  <Field label="System Location Description">
                    {warehouse.warehouse_name || '-'}
                  </Field>
                  <Field label="Warehouse" className="md:col-span-2">
                    {warehouse.location || '-'}
                  </Field>
                  <Field label="Active Status" className="md:col-span-2">
                    <Badge variant={warehouse.is_active ? 'success' : 'secondary'} appearance="ghost">
                      {warehouse.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </Field>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="planning" className="mt-6">
              <Card>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-6">
                  <Field label="Available for planning" className="md:col-span-2">
                    <Badge
                      variant={warehouse.counts_as_available === false ? 'secondary' : 'success'}
                      appearance="ghost"
                    >
                      {warehouse.counts_as_available === false ? 'Excluded' : 'Counted'}
                    </Badge>
                  </Field>
                  <Field label="Draws stock from">{poolCode || 'Stands alone'}</Field>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </Container>

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        description={`Delete warehouse ${warehouse.warehouse_code}? This action cannot be undone.`}
        successMessage="Warehouse deleted"
        // The dialog wraps this in its own mutation, which owns the toast and the
        // invalidation. Going through useDeleteWarehouse as well would report every
        // outcome twice, in two positions (see ticket-management/tickets/[id] for the
        // same shape).
        onDelete={async () => {
          await deleteWarehouse(id);
        }}
        onSuccess={() => router.push('/inventory-management/warehouses')}
        queryKeysToInvalidate={[['warehouses']]}
      />
    </>
  );
}
