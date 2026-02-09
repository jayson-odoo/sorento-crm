import { apiFetch } from '@/lib/api';
import type { FormSection, FormField } from '../types/form.types';

export async function createFormSection(formId: string, sectionName: string, sectionOrder: number): Promise<FormSection> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${formId}/sections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section_name: sectionName, section_order: sectionOrder }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create form section' }));
    throw new Error(error.message);
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
    const error = await response.json().catch(() => ({ message: 'Failed to update form section' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteFormSection(sectionId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete form section' }));
    throw new Error(error.message);
  }
}

export async function createFormField(sectionId: string, fieldData: Partial<FormField>): Promise<FormField> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}/fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fieldData),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create form field' }));
    throw new Error(error.message);
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
    const error = await response.json().catch(() => ({ message: 'Failed to update form field' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteFormField(fieldId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/form-fields/${fieldId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete form field' }));
    throw new Error(error.message);
  }
}

export async function reorderFormSections(formId: string, sectionOrders: Array<{ section_id: string; section_order: number }>): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/forms/${formId}/sections/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section_orders: sectionOrders }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to reorder form sections' }));
    throw new Error(error.message);
  }
}

export async function reorderFormFields(sectionId: string, fieldOrders: Array<{ field_id: string; field_order: number }>): Promise<void> {
  const response = await apiFetch(`/api/v1/forms-management/form-sections/${sectionId}/fields/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field_orders: fieldOrders }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to reorder form fields' }));
    throw new Error(error.message);
  }
}
