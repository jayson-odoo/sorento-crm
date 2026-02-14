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
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertIcon } from '@/components/ui/alert';
import { useUploadAttachment, useAttachmentTypesList } from '../hooks/useAttachments';
import type { AttachmentType } from '../../attachment-types/types/attachmentType.types';
import { toast } from 'sonner';

interface AttachmentUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (attachmentId?: string) => void;
  entityType?: string;
  entityId?: string;
  /** When opening from browser with a folder selected, uploads go to this directory. */
  defaultDirectoryId?: string | null;
}

export default function AttachmentUploadDialog({
  open,
  onOpenChange,
  onSuccess,
  entityType: propEntityType,
  entityId: propEntityId,
  defaultDirectoryId,
}: AttachmentUploadDialogProps) {
  const [selectedTypeId, setSelectedTypeId] = useState<string>('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [entityType, setEntityType] = useState<string>(propEntityType || '');
  const [entityId, setEntityId] = useState<string>(propEntityId || '');
  const [accessLevels, setAccessLevels] = useState<string[]>(['dealer', 'end_user']);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string>('');
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [isUploading, setIsUploading] = useState(false);

  const { data: attachmentTypes = [], isLoading: isLoadingTypes } = useAttachmentTypesList();
  const uploadMutation = useUploadAttachment();

  const selectedType = attachmentTypes.find((type: AttachmentType) => type.id === selectedTypeId);

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setSelectedTypeId('');
      setSelectedFiles([]);
      setEntityType(propEntityType || '');
      setEntityId(propEntityId || '');
      setAccessLevels(['dealer', 'end_user']);
      setValidationError('');
      setUploadProgress({});
      setIsUploading(false);
    }
  }, [open, propEntityType, propEntityId]);

  // Update validation when type or files change
  useEffect(() => {
    if (selectedFiles.length > 0 && selectedType) {
      const invalidFiles = selectedFiles.filter(file => !validateFile(file, selectedType, false));
      if (invalidFiles.length > 0) {
        setValidationError(`${invalidFiles.length} file(s) failed validation`);
      } else {
        setValidationError('');
      }
    } else {
      setValidationError('');
    }
  }, [selectedFiles, selectedType]);

  const validateFile = (file: File, type: AttachmentType, showError: boolean = true): boolean => {
    // Check file extension
    const allowedExtensions = type.allowed_extensions
      .split(',')
      .map((ext) => ext.trim().toLowerCase().replace('.', ''));
    const fileExt = file.name.split('.').pop()?.toLowerCase();

    if (!fileExt || !allowedExtensions.includes(fileExt)) {
      if (showError) {
        setValidationError(
          `File extension .${fileExt} is not allowed. Allowed extensions: ${type.allowed_extensions}`
        );
      }
      return false;
    }

    // Check file size
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > type.max_file_size_mb) {
      if (showError) {
        setValidationError(
          `File size (${fileSizeMB.toFixed(2)} MB) exceeds maximum allowed size (${type.max_file_size_mb} MB)`
        );
      }
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
        if (!selectedType) {
          setValidationError('Please select an attachment type first');
          return;
        }
        
        const files = Array.from(e.dataTransfer.files);
        const validFiles = files.filter(file => validateFile(file, selectedType, false));
        
        if (validFiles.length === 0) {
          setValidationError('No valid files found. Please check file extensions and sizes.');
          return;
        }
        
        if (validFiles.length < files.length) {
          setValidationError(`${files.length - validFiles.length} file(s) were skipped due to validation errors.`);
        }
        
        setSelectedFiles(prev => [...prev, ...validFiles]);
      }
    },
    [selectedType]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        if (!selectedType) {
          setValidationError('Please select an attachment type first');
          return;
        }
        
        const files = Array.from(e.target.files);
        const validFiles = files.filter(file => validateFile(file, selectedType, false));
        
        if (validFiles.length === 0) {
          setValidationError('No valid files found. Please check file extensions and sizes.');
          return;
        }
        
        if (validFiles.length < files.length) {
          setValidationError(`${files.length - validFiles.length} file(s) were skipped due to validation errors.`);
        }
        
        setSelectedFiles(prev => [...prev, ...validFiles]);
        
        // Reset input to allow selecting the same files again
        e.target.value = '';
      }
    },
    [selectedType]
  );
  
  const removeFile = (index: number) => {
    const fileToRemove = selectedFiles[index];
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    if (fileToRemove) {
      setUploadProgress(prev => {
        const newProgress = { ...prev };
        delete newProgress[fileToRemove.name];
        return newProgress;
      });
    }
  };

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

    if (selectedFiles.length === 0) {
      setValidationError('Please select at least one file to upload');
      return;
    }

    if (validationError && !validationError.includes('skipped')) {
      return;
    }

    setIsUploading(true);
    const uploadedIds: string[] = [];
    let hasError = false;

    try {
      // Upload files sequentially so each triggers N8N integration
      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        try {
          setUploadProgress(prev => ({ ...prev, [file.name]: 0 }));
          
          const attachment = await uploadMutation.mutateAsync({
            file: file,
            attachmentTypeId: selectedTypeId,
            entityType: entityType || propEntityType || undefined,
            entityId: entityId || propEntityId || undefined,
            accessLevels,
            directoryId: defaultDirectoryId ?? undefined,
          });
          
          uploadedIds.push(attachment.id);
          setUploadProgress(prev => ({ ...prev, [file.name]: 100 }));
        } catch (error) {
          hasError = true;
          setUploadProgress(prev => ({ ...prev, [file.name]: -1 })); // -1 indicates error
          // Continue with next file even if one fails
        }
      }

      if (uploadedIds.length > 0) {
        if (uploadedIds.length === selectedFiles.length) {
          toast.success(`Successfully uploaded ${uploadedIds.length} file${uploadedIds.length !== 1 ? 's' : ''}`);
        } else {
          toast.warning(`Uploaded ${uploadedIds.length} of ${selectedFiles.length} files. Some files failed.`);
        }
        onSuccess?.(uploadedIds[0]); // Pass first ID for compatibility
        onOpenChange(false);
      } else if (hasError) {
        setValidationError('All files failed to upload. Please try again.');
        toast.error('All files failed to upload. Please try again.');
      }
    } catch (error) {
      // Error is handled by the mutation hook (toast)
      setValidationError('Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
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
                setSelectedFiles([]);
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
              <p className="text-xs text-muted-foreground mt-1">
                Allowed: {selectedType.allowed_extensions} • Max size: {selectedType.max_file_size_mb} MB
              </p>
            )}
          </div>

          {/* File Upload */}
          <div className="space-y-2">
            <Label>Files <span className="text-destructive">*</span></Label>
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                dragActive ? 'border-primary bg-primary/5' : 'border-border'
              }`}
            >
              {selectedFiles.length > 0 ? (
                <div className="space-y-3">
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {selectedFiles.map((file, index) => (
                      <div key={`${file.name}-${index}`} className="flex items-center gap-3 p-3 border rounded-lg bg-muted/50">
                        <FileIcon className="size-5 text-muted-foreground flex-shrink-0" />
                        <div className="flex-1 min-w-0 text-left">
                          <p className="text-sm font-medium truncate">{file.name}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{formatFileSize(file.size)}</p>
                          {uploadProgress[file.name] !== undefined && uploadProgress[file.name] >= 0 && (
                            <div className="mt-1.5">
                              <div className="h-1 bg-muted rounded-full overflow-hidden">
                                <div 
                                  className="h-full bg-primary transition-all duration-300"
                                  style={{ width: `${uploadProgress[file.name]}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {uploadProgress[file.name] === -1 && (
                            <p className="text-xs text-destructive mt-0.5">Upload failed</p>
                          )}
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeFile(index)}
                          disabled={isUploading}
                        >
                          <X className="size-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                  {!isUploading && (
                    <div className="pt-2 border-t">
                      <input
                        type="file"
                        multiple
                        accept={getAcceptString(selectedType)}
                        onChange={handleFileInput}
                        className="hidden"
                        id="file-upload"
                        disabled={!selectedTypeId}
                      />
                      <label htmlFor="file-upload">
                        <Button variant="outline" asChild disabled={!selectedTypeId} size="sm">
                          <span>Add More Files</span>
                        </Button>
                      </label>
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <Upload className="size-8 mx-auto mb-3 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground mb-2">
                    Drag and drop files here, or click to browse
                  </p>
                  <input
                    type="file"
                    multiple
                    accept={getAcceptString(selectedType)}
                    onChange={handleFileInput}
                    className="hidden"
                    id="file-upload"
                    disabled={!selectedTypeId}
                  />
                  <label htmlFor="file-upload">
                    <Button variant="outline" asChild disabled={!selectedTypeId}>
                      <span>Select Files</span>
                    </Button>
                  </label>
                  {selectedType && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Max file size: {selectedType.max_file_size_mb} MB per file
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
              <p className="text-xs text-muted-foreground mt-1">
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
              <p className="text-xs text-muted-foreground mt-1">
                Link this attachment to a specific entity
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Access Levels</Label>
            <div className="flex flex-wrap gap-4">
              {['dealer', 'end_user'].map((level) => {
                const checked = accessLevels.includes(level);
                return (
                  <label key={level} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(value) => {
                        const next = new Set(accessLevels);
                        if (value) {
                          next.add(level);
                        } else {
                          next.delete(level);
                        }
                        setAccessLevels(Array.from(next));
                      }}
                    />
                    {level === 'dealer' ? 'Dealer' : 'End User'}
                  </label>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              This will be sent to the webhook for product attachment linking.
            </p>
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
            disabled={!selectedTypeId || selectedFiles.length === 0 || (!!validationError && !validationError.includes('skipped')) || isUploading}
          >
            {isUploading 
              ? `Uploading ${selectedFiles.filter(file => uploadProgress[file.name] === 100).length + 1} of ${selectedFiles.length}...` 
              : `Upload ${selectedFiles.length} Attachment${selectedFiles.length !== 1 ? 's' : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
