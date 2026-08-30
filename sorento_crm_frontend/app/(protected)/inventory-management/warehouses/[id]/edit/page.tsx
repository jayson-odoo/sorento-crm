'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WarehouseForm from '../../components/WarehouseForm';

export default function EditWarehousePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Warehouse"
          actions={
            <Button asChild variant="outline">
              <Link href={`/inventory-management/warehouses/${id}`}>
                <MoveLeft /> Back to warehouse
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <WarehouseForm
          warehouseId={id}
          onSuccess={() => {
            router.push(`/inventory-management/warehouses/${id}`);
          }}
        />
      </Container>
    </>
  );
}
