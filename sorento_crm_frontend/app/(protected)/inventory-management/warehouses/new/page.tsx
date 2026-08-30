'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WarehouseForm from '../components/WarehouseForm';

export default function NewWarehousePage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Warehouse"
          actions={
            <Button asChild variant="outline">
              <Link href="/inventory-management/warehouses">
                <MoveLeft /> Back to warehouses
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <WarehouseForm
          warehouseId={undefined}
          onSuccess={() => {
            router.push('/inventory-management/warehouses');
          }}
        />
      </Container>
    </>
  );
}
