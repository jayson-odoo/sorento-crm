'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft, Edit } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useBackToListHref } from '@/components/common/BackToList';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useSupplier, suppliersPagerQuery } from '../../hooks/useSuppliers';
import { formatDate } from '@/lib/helpers';
import DetailActions from '@/components/common/DetailActions';
import { useSupplierActions } from '../../actions';

interface SupplierDetailProps {
  supplierId: string;
}

export default function SupplierDetail({ supplierId }: SupplierDetailProps) {
  const router = useRouter();
  const backHref = useBackToListHref('/procurement-management/suppliers');
  const { data: supplier, isLoading } = useSupplier(supplierId);
  const { actions, dialogs } = useSupplierActions(supplier, {
    onDeleted: () => router.push(backHref),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!supplier) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Supplier not found</p>
        <Button variant="outline" onClick={() => router.push('/procurement-management/suppliers')} className="mt-4">
          <ArrowLeft className="size-4" />
          Back to Suppliers
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{supplier.supplier_name}</h1>
            <Badge variant={supplier.is_active ? 'success' : 'secondary'} appearance="ghost">
              {supplier.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Supplier Code: {supplier.supplier_code}
          </p>
        </div>
        <DetailActions
          pager={{
            ...suppliersPagerQuery,
            detailPath: '/procurement-management/suppliers',
            currentId: supplierId,
            ariaLabel: 'supplier',
          }}
          actions={actions}
          dialogs={dialogs}
          gearLabel="Supplier options"
          primary={
            <Button
              onClick={() =>
                router.push(`/procurement-management/suppliers/${supplierId}/edit`)
              }
            >
              <Edit className="size-4" />
              Edit
            </Button>
          }
        />
      </div>


      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Contact Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Contact Name</p>
              <p className="font-medium">{supplier.contact_name || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Email</p>
              <p className="font-medium">{supplier.email || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Phone</p>
              <p className="font-medium">{supplier.phone_number || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Address</p>
              <p className="font-medium">
                {supplier.address_line1 && (
                  <>
                    {supplier.address_line1}
                    {supplier.address_line2 && <>, {supplier.address_line2}</>}
                    <br />
                    {supplier.city && supplier.state && (
                      <>
                        {supplier.city}, {supplier.state} {supplier.postal_code}
                        <br />
                      </>
                    )}
                    {supplier.country}
                  </>
                )}
                {!supplier.address_line1 && '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Payment Terms</p>
              <p className="font-medium">{supplier.payment_terms_days} days</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Supplier Code</p>
              <p className="font-medium">{supplier.supplier_code}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge variant={supplier.is_active ? 'success' : 'secondary'} appearance="ghost">
                {supplier.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Created</p>
              <p className="font-medium text-sm">{formatDate(new Date(supplier.created_at))}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* TODO: Linked products grid, performance rating, recent orders, attachments */}
    </div>
  );
}
