'use client';

interface PDFViewerProps {
  filePath: string;
}

export default function PDFViewer({ filePath }: PDFViewerProps) {
  // TODO: Implement PDF viewer using react-pdf-viewer
  return (
    <div className="text-sm text-muted-foreground">
      PDF viewer will be displayed here using react-pdf-viewer
    </div>
  );
}
