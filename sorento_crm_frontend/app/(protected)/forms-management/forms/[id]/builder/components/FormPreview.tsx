'use client';

interface FormPreviewProps {
  formId: string;
}

export default function FormPreview({ formId }: FormPreviewProps) {
  // TODO: Implement live preview with responsive toggle
  return (
    <div className="text-sm text-muted-foreground">
      Live form preview will be displayed here
    </div>
  );
}
