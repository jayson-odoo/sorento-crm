export interface LinkedEntityRef {
  id: string;
  name: string;
  description?: string | null;
  link_id?: string | null; // ProductAttachment/PromotionAttachment id for unlink; form uses id
}

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
  directory_id?: string | null;
  full_directory_path?: string | null;  // e.g. "SORENTO CABANA (DEALER) --> SORENTO --> Product Photo --> Angle Valve"
  description?: string | null;
  access_levels?: string[] | null;  // e.g. ["dealer", "end_user"]
  entity_display_name?: string | null;
  linked_products?: LinkedEntityRef[];
  linked_promotions?: LinkedEntityRef[];
  linked_form?: LinkedEntityRef | null;
  linked_packing_lists?: LinkedEntityRef[];
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

// Nested attachment shape returned by product-attachments API (AttachmentSimple)
export interface AttachmentSimple {
  id: string;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size_bytes?: number | null;
  mime_type?: string | null;
  uploaded_at: Date | string;
  attachment_type?: AttachmentTypeSimple | null;
  full_directory_path?: string | null;
  access_levels?: string[] | null;
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
  directory_id?: string | null;
  full_directory_path?: string | null;
  description?: string | null;
  access_levels?: string[] | null;
  entity_display_name?: string | null;
  linked_products?: LinkedEntityRef[];
  linked_promotions?: LinkedEntityRef[];
  linked_form?: LinkedEntityRef | null;
  linked_packing_lists?: LinkedEntityRef[];
  uploaded_by?: string | null;
  uploaded_at: Date | string;
  is_deleted: boolean;
  deleted_at?: Date | string | null;
  deleted_by?: string | null;
  attachment_type?: AttachmentTypeSimple | null;
}
