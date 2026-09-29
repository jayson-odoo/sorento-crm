import { describe, it, expect } from 'vitest';
import {
  BUTTON_LINK_VARIABLES,
  PARAM_VARIABLES,
  renderTemplateBody,
  USE_CASES,
} from './whatsappTemplateService';

describe('renderTemplateBody', () => {
  it('fills positional params', () => {
    expect(
      renderTemplateBody('Hi {{1}}, status: {{2}}', { '1': 'Ms Ang', '2': 'approved' }),
    ).toBe('Hi Ms Ang, status: approved');
  });

  it('leaves unfilled params as placeholders', () => {
    expect(renderTemplateBody('Hi {{1}}, {{2}}', { '1': 'Ms Ang' })).toBe('Hi Ms Ang, {{2}}');
  });

  it('treats whitespace-only values as unfilled', () => {
    expect(renderTemplateBody('Hi {{1}}', { '1': '   ' })).toBe('Hi {{1}}');
  });

  it('repeats a param used multiple times', () => {
    expect(renderTemplateBody('{{1}} and {{1}}', { '1': 'x' })).toBe('x and x');
  });
});

describe('USE_CASES', () => {
  it('lists ideation_draft_reminder with its label', () => {
    const entry = USE_CASES.find((u) => u.key === 'ideation_draft_reminder');
    expect(entry?.label).toBe('Ideation - Draft Reminder');
  });

  it('lists supplier_request_chat with its label, grouped as chat', () => {
    const entry = USE_CASES.find((u) => u.key === 'supplier_request_chat');
    expect(entry?.label).toBe('Supplier Request - Chat Reply');
    expect(entry?.group).toBe('chat');
  });

  it('lists ideation_status_update with its label, in the status update group (#1355)', () => {
    const entry = USE_CASES.find((u) => u.key === 'ideation_status_update');
    expect(entry?.label).toBe('Ideation - Status Update');
    expect(entry?.group).toBeUndefined();
  });
});

describe('PARAM_VARIABLES for ideation_status_update (#1355)', () => {
  it('offers idea number, new status label and track link', () => {
    const labels = Object.fromEntries(PARAM_VARIABLES.map((v) => [v.key, v.label]));
    expect(labels['idea_number']).toBe('Idea number');
    expect(labels['status_label']).toBe('New status label');
    expect(labels['track_url']).toBe('Track link');
  });

  it('offers the track link for a URL button', () => {
    expect(BUTTON_LINK_VARIABLES).toContain('track_url');
  });
});
