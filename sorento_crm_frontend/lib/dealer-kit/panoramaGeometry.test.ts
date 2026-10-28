import { describe, expect, it } from 'vitest';

import {
  clampLook,
  horizontalFov,
  lookVector,
  maxCameraFov,
  sphereSegment,
} from './panoramaGeometry';

describe('sphereSegment', () => {
  it('covers the whole sphere for a 360 photo', () => {
    const segment = sphereSegment(360, 180);
    expect(segment.phiLength).toBeCloseTo(2 * Math.PI);
    expect(segment.thetaStart).toBeCloseTo(0);
    expect(segment.thetaLength).toBeCloseTo(Math.PI);
  });

  it('centres a partial stitch on the starting view', () => {
    const segment = sphereSegment(180, 60);
    expect(segment.phiStart + segment.phiLength / 2).toBeCloseTo(0);
    expect(segment.thetaStart + segment.thetaLength / 2).toBeCloseTo(Math.PI / 2);
  });
});

describe('maxCameraFov', () => {
  it('never zooms out past a short panorama', () => {
    expect(maxCameraFov(300, 50, 16 / 9)).toBe(50);
  });

  it('never zooms out past a narrow panorama', () => {
    const fov = maxCameraFov(80, 60, 2);
    expect(horizontalFov(fov, 2)).toBeCloseTo(80);
  });

  it('allows the full range on a sphere', () => {
    expect(maxCameraFov(360, 180, 1)).toBe(90);
  });
});

describe('clampLook', () => {
  it('stops at the edge of a partial panorama', () => {
    const { lon, lat } = clampLook(500, 80, 200, 60, 40, 1);
    expect(lon).toBeCloseTo(100 - horizontalFov(40, 1) / 2);
    expect(lat).toBeCloseTo(10);
  });

  it('wraps a full turn instead of stopping', () => {
    expect(clampLook(370, 0, 360, 180, 60, 1).lon).toBeCloseTo(10);
    expect(clampLook(-190, 0, 360, 180, 60, 1).lon).toBeCloseTo(170);
  });

  it('pins a panorama narrower than the view to its centre', () => {
    expect(clampLook(20, 20, 50, 40, 60, 1)).toEqual({ lon: 0, lat: 0 });
  });
});

describe('lookVector', () => {
  it('starts at the centre of the segment', () => {
    const [x, y, z] = lookVector(0, 0);
    expect([x, y, z].map((n) => Math.round(n * 1000) / 1000)).toEqual([1, 0, 0]);
  });
});
