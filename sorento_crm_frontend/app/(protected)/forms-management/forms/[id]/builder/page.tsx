import FormBuilder from './components/FormBuilder';

export default function FormBuilderPage({ params }: { params: { id: string } }) {
  return <FormBuilder formId={params.id} />;
}
