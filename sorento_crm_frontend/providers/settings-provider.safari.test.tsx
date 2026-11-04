/**
 * CLIENT-ERROR-REPORT, Safari root cause (crew repro with Playwright WebKit): the
 * SettingsProvider threw on mount, which is "The app could not start" on every page.
 * (1) Safari < 15.4 has no structuredClone. (2) Safari with storage blocked throws
 * SecurityError on any localStorage access.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { SettingsProvider, useSettings } from './settings-provider';

function Probe() {
  const { getOption, storeOption } = useSettings();
  return (
    <button type="button" onClick={() => storeOption('container', 'fluid')}>
      {String(getOption('container'))}
    </button>
  );
}

const realStructuredClone = globalThis.structuredClone;
const realLocalStorage = Object.getOwnPropertyDescriptor(window, 'localStorage')!;

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  globalThis.structuredClone = realStructuredClone;
  Object.defineProperty(window, 'localStorage', realLocalStorage);
  vi.restoreAllMocks();
});

describe('SettingsProvider in old or locked-down Safari', () => {
  it('renders without structuredClone (Safari < 15.4)', () => {
    // @ts-expect-error simulating a browser without it
    delete globalThis.structuredClone;
    expect(typeof globalThis.structuredClone).toBe('undefined');
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>,
    );
    expect(screen.getByRole('button').textContent).toBe('fixed');
  });

  it('renders and keeps settings in memory when localStorage throws SecurityError', () => {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new DOMException('The operation is insecure.', 'SecurityError');
      },
    });
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>,
    );
    const button = screen.getByRole('button');
    expect(button.textContent).toBe('fixed');
    button.click();
    return Promise.resolve().then(() => {
      expect(screen.getByRole('button').textContent).toBe('fluid');
    });
  });

  it('still reads stored settings when storage works', () => {
    window.localStorage.setItem('app_settings_container', JSON.stringify('fluid'));
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>,
    );
    expect(screen.getByRole('button').textContent).toBe('fluid');
    window.localStorage.removeItem('app_settings_container');
  });
});
