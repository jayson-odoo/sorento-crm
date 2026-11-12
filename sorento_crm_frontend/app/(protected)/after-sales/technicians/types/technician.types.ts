export type EmploymentType = 'employee' | 'contractor';

export interface Technician {
  id: string;
  name: string;
  phone: string | null;
  employment_type: string | null;
  is_active: boolean;
}

export interface TechnicianFormValues {
  name: string;
  phone: string | null;
  employment_type: EmploymentType;
}
