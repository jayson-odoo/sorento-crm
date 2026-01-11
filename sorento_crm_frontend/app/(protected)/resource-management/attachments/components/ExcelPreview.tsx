'use client';

interface ExcelPreviewProps {
  filePath: string;
}

export default function ExcelPreview({ filePath }: ExcelPreviewProps) {
  // TODO: Implement Excel preview using xlsx library
  return (
    <div className="text-sm text-muted-foreground">
      Excel preview will be displayed here
    </div>
  );
}
