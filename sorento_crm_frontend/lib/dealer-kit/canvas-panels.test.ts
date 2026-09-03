/**
 * The Design canvas's side-panel widths and collapsed state must survive a
 * reload and be shared between the request designer and the template editor
 * (D7, AC-S1-5) - one localStorage key, one shape. A corrupt or foreign value
 * under that key must never crash the editor; it just falls back to the
 * default layout (AC-S1-8).
 */
import { afterEach, describe, expect, it } from 'vitest';

import {
  DEFAULT_PANEL_LAYOUT,
  LEFT_MAX_PX,
  LEFT_MIN_PX,
  RAIL_MIN_PX,
  RIGHT_MAX_PX,
  RIGHT_MIN_PX,
  STORAGE_KEY,
  clampLeft,
  clampRailSplit,
  clampRight,
  readPanelLayout,
  writePanelLayout,
  type PanelLayout,
} from './canvas-panels';

afterEach(() => {
  window.localStorage.clear();
});

describe('clampLeft / clampRight / clampRailSplit', () => {
  it('keeps the left column between 180 and 480px (AC-S1-1)', () => {
    expect(clampLeft(0)).toBe(LEFT_MIN_PX);
    expect(clampLeft(300)).toBe(300);
    expect(clampLeft(9999)).toBe(LEFT_MAX_PX);
  });

  it('keeps the right column between 200 and 480px (AC-S1-2)', () => {
    expect(clampRight(0)).toBe(RIGHT_MIN_PX);
    expect(clampRight(300)).toBe(300);
    expect(clampRight(9999)).toBe(RIGHT_MAX_PX);
  });

  it('never lets the rail split go below 96px (AC-S1-4)', () => {
    expect(clampRailSplit(10)).toBe(RAIL_MIN_PX);
    expect(clampRailSplit(200)).toBe(200);
  });
});

describe('readPanelLayout / writePanelLayout', () => {
  it('returns the default layout when nothing is stored', () => {
    expect(readPanelLayout()).toEqual(DEFAULT_PANEL_LAYOUT);
  });

  it('round-trips a layout through write then read', () => {
    const layout: PanelLayout = {
      left: 260,
      right: 300,
      railSplit: 220,
      leftCollapsed: true,
      rightCollapsed: false,
    };
    writePanelLayout(layout);
    expect(readPanelLayout()).toEqual(layout);
  });

  it('clamps an out-of-range stored value on read (AC-S1-8)', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        left: 10,
        right: 9999,
        railSplit: -50,
        leftCollapsed: false,
        rightCollapsed: true,
      }),
    );
    expect(readPanelLayout()).toEqual({
      left: LEFT_MIN_PX,
      right: RIGHT_MAX_PX,
      railSplit: RAIL_MIN_PX,
      leftCollapsed: false,
      rightCollapsed: true,
    });
  });

  it('falls back to the default layout for a corrupt value (AC-S1-8)', () => {
    window.localStorage.setItem(STORAGE_KEY, '{not json');
    expect(readPanelLayout()).toEqual(DEFAULT_PANEL_LAYOUT);
  });

  it('falls back to the default layout for a value of the wrong shape (AC-S1-8)', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ foo: 'bar' }));
    expect(readPanelLayout()).toEqual(DEFAULT_PANEL_LAYOUT);
  });

  it('falls back to the default layout for a bare array', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([1, 2, 3]));
    expect(readPanelLayout()).toEqual(DEFAULT_PANEL_LAYOUT);
  });
});
