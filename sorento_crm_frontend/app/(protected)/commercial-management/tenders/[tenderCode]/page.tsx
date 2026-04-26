import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import TenderDetailClient from '../components/TenderDetailClient';

export const metadata: Metadata = {
  title: 'Tender',
};

type Props = { params: Promise<{ tenderCode: string }> };

export default async function TenderDetailPage({ params }: Props) {
  const { tenderCode } = await params;
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Tender</ToolbarTitle>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container>
        <TenderDetailClient tenderCode={decodeURIComponent(tenderCode)} />
      </Container>
    </>
  );
}
