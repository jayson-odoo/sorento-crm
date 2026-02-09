import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { PublicHoliday, PublicHolidayFormData, WorkCalendarConfig } from '../types/workCalendar.types';

export async function getWorkCalendarConfig(): Promise<WorkCalendarConfig> {
  const response = await apiFetch('/api/v1/system/work-calendar-config');
  if (!response.ok) throw new Error('Failed to fetch work calendar config');
  return response.json();
}

export async function updateWorkCalendarConfig(
  data: Partial<WorkCalendarConfig>,
): Promise<WorkCalendarConfig> {
  const response = await apiFetch('/api/v1/system/work-calendar-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update work calendar config');
  return response.json();
}

export async function getPublicHolidays(
  params: DataGridApiFetchParams & { year?: number },
): Promise<DataGridApiResponse<PublicHoliday>> {
  const { pageIndex, pageSize, year } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(year ? { year: String(year) } : {}),
  });
  const response = await apiFetch(`/api/v1/system/public-holidays?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch public holidays');
  return response.json();
}

export async function createPublicHoliday(
  data: PublicHolidayFormData,
): Promise<PublicHoliday> {
  const response = await apiFetch('/api/v1/system/public-holidays', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create public holiday');
  return response.json();
}

export async function updatePublicHoliday(
  id: string,
  data: Partial<PublicHolidayFormData>,
): Promise<PublicHoliday> {
  const response = await apiFetch(`/api/v1/system/public-holidays/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update public holiday');
  return response.json();
}

export async function deletePublicHoliday(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/system/public-holidays/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete public holiday');
}
