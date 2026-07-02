import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { FormSection, FormField } from '../types/form.types';

export async function createFormSection(formId: string, sectionName: string, sectionOrder: number): Promise<FormSection> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${formId}/sections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section_name: sectionName, section_order: sectionOrder }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create form section'));
  }
  return response.json();
}

export async function updateFormSection(sectionId: string, data: Partial<{ section_name: string; section_order: number }>): Promise<FormSection> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update form section'));
  }
  return response.json();
}

export async function deleteFormSection(sectionId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete form section'));
  }
}

export async function createFormField(sectionId: string, fieldData: Partial<FormField>): Promise<FormField> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}/fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fieldData),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create form field'));
  }
  return response.json();
}

export async function updateFormField(fieldId: string, fieldData: Partial<FormField>): Promise<FormField> {
  const response = await apiFetch(`/api/v1/forms-management/form-fields/${fieldId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fieldData),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update form field'));
  }
  return response.json();
}

export async function deleteFormField(fieldId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/form-fields/${fieldId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete form field'));
  }
}

export async function reorderFormSections(formId: string, sectionOrders: Array<{ section_id: string; section_order: number }>): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${formId}/sections/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section_orders: sectionOrders }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to reorder form sections'));
  }
}

export async function reorderFormFields(sectionId: string, fieldOrders: Array<{ field_id: string; field_order: number }>): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}/fields/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field_orders: fieldOrders }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to reorder form fields'));
  }
}
