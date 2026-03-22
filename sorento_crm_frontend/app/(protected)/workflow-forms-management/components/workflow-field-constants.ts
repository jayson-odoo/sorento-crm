import type { WorkflowFieldType } from '../types/workflowForms.types';

export const FIELD_TYPES: WorkflowFieldType[] = [
  'text',
  'textarea',
  'number',
  'email',
  'date',
  'datetime',
  'date_range',
  'select',
  'multi_select',
  'checkbox',
  'radio',
  'url',
  'phone',
];

export const CHOICE_FIELD_TYPES: WorkflowFieldType[] = ['select', 'multi_select', 'radio'];

export function fieldUsesChoices(t: WorkflowFieldType): boolean {
  return CHOICE_FIELD_TYPES.includes(t);
}
