import SupplierDetail from './components/SupplierDetail';

export default function SupplierDetailPage({ params }: { params: { id: string } }) {
  return <SupplierDetail supplierId={params.id} />;
}
