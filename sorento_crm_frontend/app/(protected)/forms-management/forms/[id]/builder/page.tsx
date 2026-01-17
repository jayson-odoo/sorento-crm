import { use } from 'react';
import FormBuilder from './components/FormBuilder';

export default function FormBuilderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <FormBuilder formId={id} />;
}
