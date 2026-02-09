export interface Attachment {
  id: string;
  attachment_type_id?: string | null;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size_bytes: number | null;
  mime_type: string | null;
  file_hash?: string | null;
  entity_type: string | null;
  entity_id: string | null;
  uploaded_by?: string | null;
  uploaded_at: Date;
  is_deleted: boolean;
  deleted_at?: Date | null;
  deleted_by?: string | null;
  virus_status?: 'clean' | 'scanning' | 'infected' | 'unknown';
  uploaded_by_user?: {
    id: string;
    name: string;
    email: string;
  };
  entity_name?: string;
  attachment_type?: AttachmentTypeSimple | null;
}

export interface AttachmentType {
  id: string;
  type_name: string;
  description?: string | null;
  allowed_extensions: string;
  max_file_size_mb: number;
  created_at: Date;
}

export interface AttachmentTypeSimple {
  id: string;
  type_name: string;
  description?: string | null;
}

export interface AttachmentResponse {
  id: string;
  attachment_type_id?: string | null;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size_bytes?: number | null;
  mime_type?: string | null;
  file_hash?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  uploaded_by?: string | null;
  uploaded_at: Date | string;
  is_deleted: boolean;
  deleted_at?: Date | string | null;
  deleted_by?: string | null;
  attachment_type?: AttachmentTypeSimple | null;
}
