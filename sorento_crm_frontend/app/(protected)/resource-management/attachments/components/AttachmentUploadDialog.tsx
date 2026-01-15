'use client';

import { useState, useCallback, useEffect } from 'react';
import { Upload, X, File as FileIcon, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertIcon } from '@/components/ui/alert';
import { useUploadAttachment, useAttachmentTypesList } from '../hooks/useAttachments';
import type { AttachmentType } from '../../attachment-types/types/attachmentType.types';

interface AttachmentUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (attachmentId?: string) => void;
  entityType?: string;
  entityId?: string;
}

export default function AttachmentUploadDialog({
  open,
  onOpenChange,
  onSuccess,
  entityType: propEntityType,
  entityId: propEntityId,
}: AttachmentUploadDialogProps) {
  const [selectedTypeId, setSelectedTypeId] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [entityType, setEntityType] = useState<string>(propEntityType || '');
  const [entityId, setEntityId] = useState<string>(propEntityId || '');
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string>('');

  const { data: attachmentTypes = [], isLoading: isLoadingTypes } = useAttachmentTypesList();
  const uploadMutation = useUploadAttachment();

  const selectedType = attachmentTypes.find((type: AttachmentType) => type.id === selectedTypeId);

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setSelectedTypeId('');
      setSelectedFile(null);
      setEntityType(propEntityType || '');
      setEntityId(propEntityId || '');
      setValidationError('');
    }
  }, [open, propEntityType, propEntityId]);

  // Update validation when type or file changes
  useEffect(() => {
    if (selectedFile && selectedType) {
      validateFile(selectedFile, selectedType);
    } else {
      setValidationError('');
    }
  }, [selectedFile, selectedType]);

  const validateFile = (file: File, type: AttachmentType) => {
    setValidationError('');

    // Check file extension
    const allowedExtensions = type.allowed_extensions
      .split(',')
      .map((ext) => ext.trim().toLowerCase().replace('.', ''));
    const fileExt = file.name.split('.').pop()?.toLowerCase();

    if (!fileExt || !allowedExtensions.includes(fileExt)) {
      setValidationError(
        `File extension .${fileExt} is not allowed. Allowed extensions: ${type.allowed_extensions}`
      );
      return false;
    }

    // Check file size
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > type.max_file_size_mb) {
      setValidationError(
        `File size (${fileSizeMB.toFixed(2)} MB) exceeds maximum allowed size (${type.max_file_size_mb} MB)`
      );
      return false;
    }

    return true;
  };

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        if (selectedType) {
          if (validateFile(file, selectedType)) {
            setSelectedFile(file);
          }
        } else {
          setValidationError('Please select an attachment type first');
        }
      }
    },
    [selectedType]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        const file = e.target.files[0];
        if (selectedType) {
          if (validateFile(file, selectedType)) {
            setSelectedFile(file);
          }
        } else {
          setValidationError('Please select an attachment type first');
        }
      }
    },
    [selectedType]
  );

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const getAcceptString = (type: AttachmentType | undefined): string => {
    if (!type) return '*';
    return type.allowed_extensions
      .split(',')
      .map((ext) => `.${ext.trim()}`)
      .join(',');
  };

  const handleUpload = async () => {
    if (!selectedTypeId) {
      setValidationError('Please select an attachment type');
      return;
    }

    if (!selectedFile) {
      setValidationError('Please select a file to upload');
      return;
    }

    if (validationError) {
      return;
    }

    try {
      const attachment = await uploadMutation.mutateAsync({
        file: selectedFile,
        attachmentTypeId: selectedTypeId,
        entityType: entityType || propEntityType || undefined,
        entityId: entityId || propEntityId || undefined,
      });

      onSuccess?.(attachment.id);
      onOpenChange(false);
    } catch (error) {
      // Error is handled by the mutation hook (toast)
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create Attachment</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Attachment Type Selection */}
          <div className="space-y-2">
            <Label htmlFor="attachment-type">
              Attachment Type <span className="text-destructive">*</span>
            </Label>
            <Select
              value={selectedTypeId}
              onValueChange={(value) => {
                setSelectedTypeId(value);
                setSelectedFile(null);
                setValidationError('');
              }}
              disabled={isLoadingTypes}
            >
              <SelectTrigger id="attachment-type">
                <SelectValue placeholder="Select attachment type" />
              </SelectTrigger>
              <SelectContent>
                {attachmentTypes.map((type: AttachmentType) => (
                  <SelectItem key={type.id} value={type.id}>
                    <div className="flex flex-col">
                      <span className="font-medium">{type.type_name}</span>
                      {type.description && (
                        <span className="text-xs text-muted-foreground">{type.description}</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedType && (
              <p className="text-xs text-muted-foreground">
                Allowed: {selectedType.allowed_extensions} • Max size: {selectedType.max_file_size_mb} MB
              </p>
            )}
          </div>

          {/* File Upload */}
          <div className="space-y-2">
            <Label>File <span className="text-destructive">*</span></Label>
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                dragActive ? 'border-primary bg-primary/5' : 'border-border'
              }`}
            >
              {selectedFile ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-3 border rounded-lg bg-muted/50">
                    <FileIcon className="size-5 text-muted-foreground" />
                    <div className="flex-1 min-w-0 text-left">
                      <p className="text-sm font-medium truncate">{selectedFile.name}</p>
                      <p className="text-xs text-muted-foreground">{formatFileSize(selectedFile.size)}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setSelectedFile(null);
                        setValidationError('');
                      }}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <Upload className="size-8 mx-auto mb-3 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground mb-2">
                    Drag and drop file here, or click to browse
                  </p>
                  <input
                    type="file"
                    accept={getAcceptString(selectedType)}
                    onChange={handleFileInput}
                    className="hidden"
                    id="file-upload"
                    disabled={!selectedTypeId}
                  />
                  <label htmlFor="file-upload">
                    <Button variant="outline" asChild disabled={!selectedTypeId}>
                      <span>Select File</span>
                    </Button>
                  </label>
                  {selectedType && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Max file size: {selectedType.max_file_size_mb} MB
                    </p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Entity Linking (Optional) */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="entity-type">Entity Type (Optional)</Label>
              <Input
                id="entity-type"
                placeholder="e.g., product, order, complaint"
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Link this attachment to a specific entity type
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="entity-id">Entity ID (Optional)</Label>
              <Input
                id="entity-id"
                placeholder="UUID"
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Link this attachment to a specific entity
              </p>
            </div>
          </div>

          {/* Validation Error */}
          {validationError && (
            <Alert variant="destructive" icon="destructive">
              <AlertIcon>
                <AlertCircle className="size-4" />
              </AlertIcon>
              <AlertDescription>{validationError}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!selectedTypeId || !selectedFile || !!validationError || uploadMutation.isPending}
          >
            {uploadMutation.isPending ? 'Uploading...' : 'Upload Attachment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
