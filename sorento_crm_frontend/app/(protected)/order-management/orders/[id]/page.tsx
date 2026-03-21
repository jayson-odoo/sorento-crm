'use client';

import { use, useMemo } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
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
import OrderDetail from '../components/OrderDetail';
import { buildOrderDetailSearch, parseOrderListNavFromSearchParams } from '../utils/orderListNavQuery';

export default function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const listQueryString = searchParams.toString();
  const listNav = useMemo(
    () => parseOrderListNavFromSearchParams(new URLSearchParams(listQueryString)),
    [listQueryString],
  );
  const ordersListHref = `/order-management/orders${buildOrderDetailSearch(listNav)}`;

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Order</ToolbarTitle>
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
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href={ordersListHref}>
                <MoveLeft /> Back to orders
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>
      <Container>
        <OrderDetail orderId={id} listNav={listNav} />
      </Container>
    </>
  );
}
