import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SPODocumentDetail } from '../components/SPODocumentDetail';

export const metadata: Metadata = {
  title: 'SPO Document',
  description: 'SPO document detail - header and lines, with plan visibility per line.',
};

export default async function SPODocumentDetailPage({
  params,
}: {
  // Still ENCODED on arrival (Q7): the ASGI/Starlette side needs `:path` to accept a
  // literal slash in an SPO number, but on the FE side a Next.js dynamic segment
  // (`[spoNumber]`) reads its own param raw, undecoded - so `SPO-2026%2F08-0061`
  // shows up here exactly as the link built it, and this route owns the ONE decode
  // (`SPODocumentDetail` and everything under it hold the decoded value).
  params: Promise<{ spoNumber: string }>;
}) {
  const { spoNumber: rawSpoNumber } = await params;
  const spoNumber = decodeURIComponent(rawSpoNumber);

  return (
    <>
      {/* Back on the page-level toolbar row, top right (UAT AC-21) - the same spot
          the Purchase Order form view puts it, not the record's own title row. */}
      <Container>
        <PageHeader
          title="SPO Document"
          actions={
            <BackToList listPath="/procurement-management/spo-allocations" label="Back to SPO Allocations" />
          }
        />
      </Container>

      <Container>
        <SPODocumentDetail spoNumber={spoNumber} />
      </Container>
    </>
  );
}
