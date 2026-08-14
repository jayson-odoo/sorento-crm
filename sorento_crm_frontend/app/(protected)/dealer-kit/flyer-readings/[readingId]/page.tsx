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
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';

import { FlyerReviewScreen } from './components/FlyerReviewScreen';

export const metadata: Metadata = {
  title: 'Review Flyer',
  description: 'Check what the system read off a flyer, then seed a draft brochure from it.',
};

export default async function DealerKitFlyerReviewRoute({
  params,
}: {
  params: Promise<{ readingId: string }>;
}) {
  const { readingId } = await params;

  return (
    <Container width="fluid">
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Review Flyer</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/dealer-kit/flyer-readings">Flyers</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Review</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>

      <FlyerReviewScreen readingId={readingId} />
    </Container>
  );
}
