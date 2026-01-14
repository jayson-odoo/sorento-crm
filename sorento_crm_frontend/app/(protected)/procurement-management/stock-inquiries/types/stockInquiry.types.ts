export interface StockInquiry {
  id: string;
  salesperson?: string | null;
  product_code?: string | null;
  item_description?: string | null;
  project_customer?: string | null;
  project_name?: string | null;
  quantity?: number | null;
  delivery_date?: Date | null;
  brand?: string | null;
  additional_remark?: string | null;
  purchasing_response?: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface StockInquiryFormData {
  salesperson?: string;
  product_code?: string;
  item_description?: string;
  project_customer?: string;
  project_name?: string;
  quantity?: number;
  delivery_date?: Date;
  brand?: string;
  additional_remark?: string;
  purchasing_response?: string;
}

export interface StockInquiryDetail extends StockInquiry {}
