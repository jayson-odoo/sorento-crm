'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import PDFViewer from './PDFViewer';
import ImageGallery from './ImageGallery';
import ExcelPreview from './ExcelPreview';
import DocumentPreview from './DocumentPreview';
import type { Attachment } from '../types/attachment.types';

interface FilePreviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachment: Attachment | null;
}

export default function FilePreviewModal({ open, onOpenChange, attachment }: FilePreviewModalProps) {
  if (!attachment) return null;

  const mimeType = attachment.mime_type || '';
  const isPDF = mimeType === 'application/pdf';
  const isImage = mimeType.startsWith('image/');
  const isExcel = mimeType.includes('spreadsheet') || attachment.original_filename.match(/\.(xls|xlsx)$/i);
  const isWord = mimeType.includes('wordprocessing') || attachment.original_filename.match(/\.(doc|docx)$/i);
  const isText = mimeType.startsWith('text/') || attachment.original_filename.match(/\.(txt|csv|json)$/i);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>{attachment.original_filename}</DialogTitle>
        </DialogHeader>
        <div className="overflow-auto">
          {isPDF && <PDFViewer filePath={attachment.file_path} />}
          {isImage && <ImageGallery filePath={attachment.file_path} />}
          {isExcel && <ExcelPreview filePath={attachment.file_path} />}
          {isWord && <DocumentPreview attachment={attachment} />}
          {isText && (
            <div className="text-sm text-muted-foreground">
              Text file preview will be displayed here
            </div>
          )}
          {!isPDF && !isImage && !isExcel && !isWord && !isText && (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground">Preview not available for this file type</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
