/**
 * PS-SPEC-SHEET (crew browser pass, step 3): on a spec sheet template the Insert field dialog
 * offers the "Spec sheet" group (project title, ref, area, ...), searchable; a price tag
 * template (which passes the price tag groups) never does.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { mergeFieldCatalog } from '@/lib/dealer-kit/merge-fields';
import { InsertFieldDialog } from './InsertFieldDialog';

function open(groups?: Parameters<typeof InsertFieldDialog>[0]['groups']) {
  render(
    <InsertFieldDialog
      open
      value=""
      data={null}
      specKeys={[]}
      groups={groups}
      onCancel={vi.fn()}
      onDone={vi.fn()}
    />,
  );
}

describe('Spec sheet fields in Insert field', () => {
  it('the catalog carries the Spec sheet group when every group is asked for', () => {
    const paths = mergeFieldCatalog([]).filter((f) => f.group === 'Spec sheet').map((f) => f.path);
    expect(paths).toEqual(
      expect.arrayContaining([
        'doc.project_title',
        'doc.ref',
        'doc.date',
        'line.area',
        'line.comment',
        'line.marker',
        'product.brand',
      ]),
    );
  });

  it('a spec sheet template finds "Project title" by search', () => {
    open(undefined);
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), {
      target: { value: 'Project title' },
    });
    expect(screen.getByText('Project title')).toBeInTheDocument();
    expect(screen.queryByText('No field matches that.')).toBeNull();
  });

  it('a price tag template does not offer it', () => {
    open(['Product', 'Specs', 'Set', 'Line', 'Combo']);
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), {
      target: { value: 'Project title' },
    });
    expect(screen.getByText('No field matches that.')).toBeInTheDocument();
  });
});
