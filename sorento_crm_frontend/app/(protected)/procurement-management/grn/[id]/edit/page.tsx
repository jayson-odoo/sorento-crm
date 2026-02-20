'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import GRNForm from '../../components/GRNForm';

type EditGRNPageProps = {
  params: Promise<{ id: string }>;
};

export default function EditGRNPage({ params }: EditGRNPageProps) {
  const { id } = use(params);

  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Edit GRN</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/procurement-management/grn">GRN</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href={`/procurement-management/grn/${id}`}>GRN</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Edit</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>
      <Container>
        <GRNForm grnId={id} />
      </Container>
    </Container>
  );
}
