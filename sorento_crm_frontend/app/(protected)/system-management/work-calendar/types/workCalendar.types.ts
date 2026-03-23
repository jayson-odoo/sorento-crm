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
  /** ISO-like time from API, e.g. "09:00:00" */
  work_day_start_time: string;
  work_day_end_time: string;
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
