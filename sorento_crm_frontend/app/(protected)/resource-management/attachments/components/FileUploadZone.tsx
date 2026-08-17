'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { FileDropzone } from '@/components/common/FileDropzone';
import { useUploadAttachment } from '../hooks/useAttachments';
import { useUploadConflict } from '@/hooks/use-upload-conflict';

interface FileUploadZoneProps {
  attachmentTypeId: string;
  entityType: string;
  entityId: string;
  acceptedTypes?: string;
  maxFileSize?: number; // in MB
  onUploadComplete?: (attachment: any) => void;
  onUploadError?: (error: Error) => void;
}

export default function FileUploadZone({
  attachmentTypeId,
  entityType,
  entityId,
  acceptedTypes = '*',
  maxFileSize = 10,
  onUploadComplete,
  onUploadError,
}: FileUploadZoneProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const uploadMutation = useUploadAttachment();
  const { runUpload, ConflictDialog } = useUploadConflict();

  const handleUpload = async () => {
    for (const file of selectedFiles) {
      try {
        const result = await runUpload((onConflict) =>
          uploadMutation.mutateAsync({
            file,
            attachmentTypeId,
            entityType,
            entityId,
            onConflict,
          })
        );
        if (result == null) {
          continue;
        }
        if (onUploadComplete) {
          // onUploadComplete will be called by mutation onSuccess
        }
      } catch (error) {
        if (onUploadError) {
          onUploadError(error as Error);
        }
      }
    }
    setSelectedFiles([]);
  };

  return (
    <div className="space-y-4">
      <FileDropzone
        multiple
        accept={acceptedTypes === '*' ? undefined : acceptedTypes}
        maxSizeMb={maxFileSize}
        files={selectedFiles}
        onFilesChange={setSelectedFiles}
        title="Drag and drop files here, or click to browse"
        aria-label="Attachment files"
      />

      {selectedFiles.length > 0 && (
        <Card>
          <CardContent className="pt-6">
            <Button
              onClick={handleUpload}
              disabled={uploadMutation.isPending}
              className="w-full"
            >
              Upload {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''}
            </Button>
          </CardContent>
        </Card>
      )}
      {ConflictDialog}
    </div>
  );
}
