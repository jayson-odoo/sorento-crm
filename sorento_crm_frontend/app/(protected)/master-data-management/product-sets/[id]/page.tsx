import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
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
        <PageHeader
          title="Product Set"
          actions={
            <BackToList
              listPath="/master-data-management/product-sets"
              label="Back to product sets"
            />
          }
        />
      </Container>

      <Container>
        <ProductSetDetail id={id} />
      </Container>
    </>
  );
}
