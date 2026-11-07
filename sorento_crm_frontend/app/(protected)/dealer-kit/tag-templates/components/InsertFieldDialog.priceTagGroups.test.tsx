/**
 * F1: the price tag editor's Insert field offers "Combo positions". The editor passes ONE shared
 * group list (`PRICE_TAG_FIELD_GROUPS`, merge-fields.ts); this goes through that list, and checks
 * the editor takes it from there instead of keeping a copy that can miss a group.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PRICE_TAG_FIELD_GROUPS } from '@/lib/dealer-kit/merge-fields';
import { InsertFieldDialog } from './InsertFieldDialog';

describe('price tag Insert field groups', () => {
  it('lists Combo positions (and not the spec sheet fields)', () => {
    render(
      <InsertFieldDialog
        open
        value=""
        data={null}
        specKeys={[]}
        groups={PRICE_TAG_FIELD_GROUPS}
        onCancel={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText('Combo positions')).toBeInTheDocument();
    expect(screen.getByText('Combo')).toBeInTheDocument();
    expect(screen.queryByText('Spec sheet')).toBeNull();
  });

  it('the canvas editor uses that shared list, not its own', () => {
    const source = readFileSync(join(__dirname, 'TagCanvasEditor.tsx'), 'utf8');
    expect(source).toContain('PRICE_TAG_FIELD_GROUPS');
    expect(source).not.toMatch(/const PRICE_TAG_FIELD_GROUPS/);
  });
});
