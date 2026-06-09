import { describe, it, expect } from 'vitest';
import { renderTemplateBody } from './whatsappTemplateService';

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
