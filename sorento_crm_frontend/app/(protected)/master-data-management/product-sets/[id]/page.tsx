import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductSetDetail from '../components/ProductSetDetail';

export default async function ProductSetDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader title="Product Set" />
      </Container>

      <Container>
        <ProductSetDetail id={id} />
      </Container>
    </>
  );
}
