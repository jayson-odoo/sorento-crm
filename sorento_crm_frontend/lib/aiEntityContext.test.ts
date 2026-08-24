import { afterEach, describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';

import {
  clearCurrentEntity,
  getCurrentEntity,
  setCurrentEntity,
} from './aiEntityContext';
import { getPageSnapshot } from './aiPageSnapshot';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';

afterEach(() => {
  clearCurrentEntity();
  document.body.innerHTML = '';
});

describe('aiEntityContext store', () => {
  it('round-trips set/get/clear', () => {
    expect(getCurrentEntity()).toBeNull();

    setCurrentEntity({ entity_type: 'complaint', id: 'abc-123' });
    expect(getCurrentEntity()).toEqual({ entity_type: 'complaint', id: 'abc-123' });

    setCurrentEntity({ entity_type: 'stock_inquiry', id: 'def-456' });
    expect(getCurrentEntity()).toEqual({ entity_type: 'stock_inquiry', id: 'def-456' });

    clearCurrentEntity();
    expect(getCurrentEntity()).toBeNull();
  });
});

describe('getPageSnapshot entity wiring', () => {
  it('includes the entity when one is set', () => {
    document.body.innerHTML =
      '<div data-ai-context>Complaint CMP-1 status rejected</div>';
    setCurrentEntity({ entity_type: 'complaint', id: 'abc-123' });

    const snapshot = getPageSnapshot();
    expect(snapshot).not.toBeNull();
    expect(snapshot?.entity).toEqual({ entity_type: 'complaint', id: 'abc-123' });
    // visible_text is still produced (entity is additive metadata, not a
    // replacement). jsdom doesn't implement layout so innerText may be empty - 
    // assert the field exists as a string rather than its content.
    expect(typeof snapshot?.visible_text).toBe('string');
  });

  it('reports entity null when cleared', () => {
    document.body.innerHTML = '<div data-ai-context>Some page</div>';
    clearCurrentEntity();

    const snapshot = getPageSnapshot();
    expect(snapshot?.entity).toBeNull();
  });
});

describe('RecordEntityRegistrar', () => {
  it('registers on mount and clears on unmount', () => {
    const { unmount } = render(
      React.createElement(RecordEntityRegistrar, {
        entityType: 'complaint',
        id: 'abc-123',
      }),
    );
    expect(getCurrentEntity()).toEqual({ entity_type: 'complaint', id: 'abc-123' });

    unmount();
    expect(getCurrentEntity()).toBeNull();
  });

  it('re-registers when id changes', () => {
    const { rerender } = render(
      React.createElement(RecordEntityRegistrar, {
        entityType: 'complaint',
        id: 'abc-123',
      }),
    );
    expect(getCurrentEntity()).toEqual({ entity_type: 'complaint', id: 'abc-123' });

    rerender(
      React.createElement(RecordEntityRegistrar, {
        entityType: 'complaint',
        id: 'xyz-789',
      }),
    );
    expect(getCurrentEntity()).toEqual({ entity_type: 'complaint', id: 'xyz-789' });
  });

  it('does not register for a "new" id', () => {
    render(
      React.createElement(RecordEntityRegistrar, {
        entityType: 'complaint',
        id: 'new',
      }),
    );
    expect(getCurrentEntity()).toBeNull();
  });

  // The registrar is generic - it just round-trips whatever entityType it's
  // given into the store. These are the strings the detail pages mount with;
  // each MUST match the backend record-context entity_type exactly.
  it.each([
    'complaint',
    'stock_inquiry',
    'purchase_request',
    'sponsorship_form',
  ])('mounts/unmounts cleanly for entityType "%s"', (entityType) => {
    const { unmount } = render(
      React.createElement(RecordEntityRegistrar, {
        entityType,
        id: 'rec-001',
      }),
    );
    expect(getCurrentEntity()).toEqual({ entity_type: entityType, id: 'rec-001' });

    unmount();
    expect(getCurrentEntity()).toBeNull();
  });
});
