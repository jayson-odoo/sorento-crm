/**
 * The maths behind the walkthrough viewer, kept out of the WebGL component so
 * it can be tested without a canvas.
 *
 * A stop's panorama covers `hFovDeg` x `vFovDeg` (360 x 180 for a full
 * sphere). It is drawn on the matching piece of a sphere, centred on the
 * direction the camera starts looking (lon 0, lat 0), and the camera is kept
 * from turning past the picture's edge into black.
 */

const DEG = Math.PI / 180;

/** Widest the camera may zoom out, before any panorama limit. */
export const MAX_CAMERA_FOV_DEG = 90;
export const MIN_CAMERA_FOV_DEG = 30;

export interface SphereSegment {
  phiStart: number;
  phiLength: number;
  thetaStart: number;
  thetaLength: number;
}

/** Arguments for `THREE.SphereGeometry`, in radians. */
export function sphereSegment(hFovDeg: number, vFovDeg: number): SphereSegment {
  const phiLength = Math.min(hFovDeg, 360) * DEG;
  const thetaLength = Math.min(vFovDeg, 180) * DEG;
  return {
    phiStart: -phiLength / 2,
    phiLength,
    thetaStart: (Math.PI - thetaLength) / 2,
    thetaLength,
  };
}

/** The camera's horizontal angle for a vertical `fovDeg` at this aspect ratio. */
export function horizontalFov(fovDeg: number, aspect: number): number {
  return (2 * Math.atan(Math.tan((fovDeg * DEG) / 2) * aspect)) / DEG;
}

/** Widest vertical camera angle that never shows past the picture's edge. */
export function maxCameraFov(hFovDeg: number, vFovDeg: number, aspect: number): number {
  let limit = Math.min(MAX_CAMERA_FOV_DEG, vFovDeg);
  // At 180 degrees or wider the camera (90 degrees tall at most) can never see
  // both edges at once, and tan() past 90 degrees would turn negative.
  if (hFovDeg < 180) {
    // The vertical angle whose horizontal spread equals the panorama's width.
    const fromWidth = (2 * Math.atan(Math.tan((hFovDeg * DEG) / 2) / aspect)) / DEG;
    limit = Math.min(limit, fromWidth);
  }
  return Math.max(limit, 1);
}

/** Keep the look direction inside the picture. Degrees in, degrees out. */
export function clampLook(
  lon: number,
  lat: number,
  hFovDeg: number,
  vFovDeg: number,
  cameraFovDeg: number,
  aspect: number,
): { lon: number; lat: number } {
  const clamp = (value: number, limit: number) =>
    limit <= 0 ? 0 : Math.max(-limit, Math.min(limit, value));

  const latLimit = Math.min(vFovDeg, 180) / 2 - cameraFovDeg / 2;
  const clampedLat = clamp(lat, Math.min(latLimit, 89));
  if (hFovDeg >= 360) {
    // A full turn wraps; keep the number small so it never loses precision.
    return { lon: ((((lon + 180) % 360) + 360) % 360) - 180, lat: clampedLat };
  }
  const lonLimit = hFovDeg / 2 - horizontalFov(cameraFovDeg, aspect) / 2;
  return { lon: clamp(lon, lonLimit), lat: clampedLat };
}

/** Unit vector the camera looks along, matching `sphereSegment`'s orientation. */
export function lookVector(lonDeg: number, latDeg: number): [number, number, number] {
  const lon = lonDeg * DEG;
  const lat = latDeg * DEG;
  return [Math.cos(lat) * Math.cos(lon), Math.sin(lat), Math.cos(lat) * Math.sin(lon)];
}
