import { Metadata } from 'next';

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';

import { FlyerSpecReviewScreen } from '../components/FlyerSpecReviewScreen';

export const metadata: Metadata = {
  title: 'Review Flyer Specs',
  description:
    'Review what a flyer says about each product, then write the rows you tick.',
};

export default async function FlyerSpecProposalsReviewRoute({
  params,
}: {
  params: Promise<{ readingId: string }>;
}) {
  const { readingId } = await params;

  return (
    <Container width="fluid">
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Review Flyer Specs</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/master-data-management/flyer-spec-proposals">
                  Flyer Spec Proposals
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Review</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>

      <FlyerSpecReviewScreen readingId={readingId} />
    </Container>
  );
}
