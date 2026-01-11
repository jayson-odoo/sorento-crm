'use client';

import { useCallback, useState } from 'react';
import { Upload, X, File as FileIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useUploadAttachment } from '../hooks/useAttachments';

interface FileUploadZoneProps {
  entityType: string;
  entityId: string;
  acceptedTypes?: string;
  maxFileSize?: number; // in MB
  onUploadComplete?: (attachment: any) => void;
  onUploadError?: (error: Error) => void;
}

export default function FileUploadZone({
  entityType,
  entityId,
  acceptedTypes = '*',
  maxFileSize = 10,
  onUploadComplete,
  onUploadError,
}: FileUploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const uploadMutation = useUploadAttachment();

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
    }
  }, []);

  const handleFiles = (files: File[]) => {
    const validFiles = files.filter((file) => {
      // Validate file type
      if (acceptedTypes !== '*') {
        const extensions = acceptedTypes.split(',').map((ext) => ext.trim().replace('.', ''));
        const fileExt = file.name.split('.').pop()?.toLowerCase();
        if (!fileExt || !extensions.includes(fileExt)) {
          return false;
        }
      }
      // Validate file size
      const fileSizeMB = file.size / (1024 * 1024);
      if (fileSizeMB > maxFileSize) {
        return false;
      }
      return true;
    });

    setSelectedFiles((prev) => [...prev, ...validFiles]);
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    for (const file of selectedFiles) {
      try {
        setUploadProgress((prev) => ({ ...prev, [file.name]: 0 }));
        // TODO: Implement progress tracking
        await uploadMutation.mutateAsync({
          file,
          entityType,
          entityId,
        });
        setUploadProgress((prev) => ({ ...prev, [file.name]: 100 }));
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
    setUploadProgress({});
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  return (
    <div className="space-y-4">
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive ? 'border-primary bg-primary/5' : 'border-border'
        }`}
      >
        <Upload className="size-8 mx-auto mb-4 text-muted-foreground" />
        <p className="text-sm text-muted-foreground mb-2">
          Drag and drop files here, or click to browse
        </p>
        <input
          type="file"
          multiple
          accept={acceptedTypes}
          onChange={handleFileInput}
          className="hidden"
          id="file-upload"
        />
        <label htmlFor="file-upload">
          <Button variant="outline" asChild>
            <span>Select Files</span>
          </Button>
        </label>
        <p className="text-xs text-muted-foreground mt-2">
          Max file size: {maxFileSize}MB
        </p>
      </div>

      {selectedFiles.length > 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="space-y-2">
              {selectedFiles.map((file, index) => (
                <div key={index} className="flex items-center gap-3 p-2 border rounded">
                  <FileIcon className="size-4 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{file.name}</p>
                    <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                    {uploadProgress[file.name] !== undefined && (
                      <Progress value={uploadProgress[file.name]} className="mt-1 h-1" />
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeFile(index)}
                    disabled={uploadProgress[file.name] !== undefined}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              onClick={handleUpload}
              disabled={uploadMutation.isPending}
              className="w-full mt-4"
            >
              Upload {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
