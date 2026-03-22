import type { WorkflowFormSchema, WorkflowHeaderField, WorkflowHeaderSection } from '../types/workflowForms.types';

const DEFAULT_SECTION_ID = 'sec_default';

export function flattenHeaderFields(schema: WorkflowFormSchema): WorkflowHeaderField[] {
  if (schema.header_sections?.length) {
    return schema.header_sections.flatMap((s) => s.fields);
  }
  return schema.header_fields ?? [];
}

/** Migrate legacy flat header_fields into header_sections (single "General" section). */
export function normalizeWorkflowFormSchema(schema: WorkflowFormSchema): WorkflowFormSchema {
  if (schema.header_sections && schema.header_sections.length > 0) {
    return {
      ...schema,
      header_fields: flattenHeaderFields(schema),
    };
  }
  const hf = schema.header_fields ?? [];
  return {
    ...schema,
    header_sections: [
      {
        id: DEFAULT_SECTION_ID,
        title: 'General',
        fields: [...hf],
      },
    ],
    header_fields: [...hf],
  };
}

export function emptyHeaderSections(): WorkflowHeaderSection[] {
  return [{ id: DEFAULT_SECTION_ID, title: 'General', fields: [] }];
}
