/**
 * S13 (reviewer finding, PR #1304): the "Contacts with their own level" count linked
 * to the unfiltered Contacts list (AC-MEM028) - a staff member could not actually get
 * to the contacts the count was counting. The link now carries `chatbot_memory_level=
 * own`, the sentinel this lane picked for "has its own level set" (`respond_contacts.
 * chatbot_memory_level IS NOT NULL`); the Contacts list itself reading that param is
 * separate backend + list-wiring work, tracked with the captain.
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import MemorySettingsCard from './MemorySettingsCard';
import type { ChatbotMemorySettings } from '../services/chatbotSettingsService';

afterEach(() => cleanup());

function settings(overrides: Partial<ChatbotMemorySettings> = {}): ChatbotMemorySettings {
  return {
    enabled: true,
    default_level: 'full',
    own_level_count: 3,
    ...overrides,
  };
}

describe('MemorySettingsCard - "Contacts with their own level" link (S13, AC-MEM028)', () => {
  it('carries chatbot_memory_level=own so the count links to the contacts it counts', () => {
    render(
      <MemorySettingsCard
        value={settings()}
        onChange={() => {}}
        isLoading={false}
        isError={false}
      />,
    );

    const link = screen.getByRole('link', { name: /3 contacts/i });
    expect(link).toHaveAttribute(
      'href',
      '/user-management/contacts?chatbot_memory_level=own',
    );
  });
});
