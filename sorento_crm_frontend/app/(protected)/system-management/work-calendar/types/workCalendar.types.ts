export interface WorkCalendarConfig {
  id: string;
  config_key: string;
  monday: boolean;
  tuesday: boolean;
  wednesday: boolean;
  thursday: boolean;
  friday: boolean;
  saturday: boolean;
  sunday: boolean;
  created_at: string;
  updated_at: string;
}

export interface PublicHoliday {
  id: string;
  date: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublicHolidayFormData {
  date: string;
  name: string;
  description?: string;
}
