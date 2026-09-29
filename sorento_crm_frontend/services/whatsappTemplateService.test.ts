import { describe, it, expect } from 'vitest';
import { renderTemplateBody, USE_CASES } from './whatsappTemplateService';

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
});
