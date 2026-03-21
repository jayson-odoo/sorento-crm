'use client';

import { use } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
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
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarActions, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import OrderForm from '../../components/OrderForm';

export default function EditOrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const listQs = searchParams.toString();
  const detailHref = listQs ? `/order-management/orders/${id}?${listQs}` : `/order-management/orders/${id}`;
  const ordersListHref = listQs ? `/order-management/orders?${listQs}` : '/order-management/orders';

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Edit Order</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Order Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href={ordersListHref}>Orders</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href={detailHref}>Order</BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href={detailHref}>
                <MoveLeft /> Back to order
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>
      <Container>
        <OrderForm
          orderId={id}
          onSuccess={() => {
            router.push(detailHref);
          }}
        />
      </Container>
    </>
  );
}
