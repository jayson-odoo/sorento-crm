'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useForm } from '../../hooks/useForms';
import FormPreview from './FormPreview';
import FormFieldEditor from './FormFieldEditor';

interface FormBuilderProps {
  formId: string;
}

export default function FormBuilder({ formId }: FormBuilderProps) {
  const { data: form, isLoading } = useForm(formId);
  const [selectedField, setSelectedField] = useState<string | null>(null);

  if (isLoading) {
    return <div className="text-center py-8">Loading form builder...</div>;
  }

  if (!form) {
    return <div className="text-center py-8">Form not found</div>;
  }

  return (
    <div className="grid grid-cols-12 gap-4 h-[calc(100vh-200px)]">
      {/* Left Panel - Form Tree (30%) */}
      <div className="col-span-3 border-r">
        <Card className="h-full">
          <CardHeader>
            <CardTitle className="text-lg">{form.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <Button size="sm" className="w-full mb-4">
              <Plus className="size-4" />
              Add Section
            </Button>
            {/* TODO: Form tree with sections and fields, drag-drop */}
            <div className="text-sm text-muted-foreground">
              Form tree will be displayed here
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Center Panel - Field Editor (40%) */}
      <div className="col-span-5 border-r">
        <Card className="h-full">
          <CardHeader>
            <CardTitle className="text-lg">Field Properties</CardTitle>
          </CardHeader>
          <CardContent>
            {selectedField ? (
              <FormFieldEditor fieldId={selectedField} />
            ) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                Select a field to edit its properties
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Right Panel - Live Preview (30%) */}
      <div className="col-span-4">
        <Card className="h-full">
          <CardHeader>
            <CardTitle className="text-lg">Live Preview</CardTitle>
          </CardHeader>
          <CardContent>
            <FormPreview formId={formId} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
