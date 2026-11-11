import { describe, expect, it } from 'vitest';
import { STATES, mapXZ, shopStateKey, siteLook, stateKeyOf } from './townMap';

describe('town map (TOWN-PROJECT-CITY)', () => {
  it('has one place for every my_state value plus the State not set islet', () => {
    const names = STATES.map((s) => s.name);
    for (const n of ['Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang', 'Perak', 'Perlis', 'Pulau Pinang', 'Sabah', 'Sarawak', 'Selangor', 'Terengganu', 'Kuala Lumpur', 'Labuan', 'Putrajaya']) {
      expect(names).toContain(n);
    }
    expect(names).toContain('State not set');
    expect(STATES).toHaveLength(17);
  });

  it('reads a snapshot state (a my_state value) as a map key; blank or unknown goes to the islet', () => {
    expect(stateKeyOf('Selangor')).toBe('selangor');
    expect(stateKeyOf(' kuala lumpur ')).toBe('kl');
    expect(stateKeyOf('Pulau Pinang')).toBe('penang');
    expect(stateKeyOf('Negeri Sembilan')).toBe('ns');
    expect(stateKeyOf(null)).toBe('notset');
    expect(stateKeyOf(undefined)).toBe('notset');
    expect(stateKeyOf('Atlantis')).toBe('notset');
  });

  it('turns the map so the live port (bearing 232) is west and Shah Alam is the origin', () => {
    expect(mapXZ(0, 0)).toEqual([0, 0]);
    const [x, z] = mapXZ(-1, 0);
    expect((Math.atan2(z, x) * 180) / Math.PI + 360).toBeCloseTo(232);
    const [nx, nz] = mapXZ(0, 1);
    expect(x * nx + z * nz).toBeCloseTo(0);
  });

  it("draws a site from the project's own dates, never from our sales stage", () => {
    const day = '2026-11-03';
    const site = (launch: string | null, delivery: string | null) => ({ launch_date: launch, delivery_date: delivery });
    expect(siteLook(site(null, null), day)).toBe('plain');
    expect(siteLook(site('2025-01-01', null), day)).toBe('plain');
    expect(siteLook(site('2027-01-01', '2026-01-01'), day)).toBe('plain');
    expect(siteLook(site('2027-01-01', '2030-01-01'), day)).toBe('before');
    expect(siteLook(site('2026-06-01', '2029-06-01'), day)).toBe('ground');
    expect(siteLook(site('2025-03-01', '2028-03-01'), day)).toBe('frame');
    expect(siteLook(site('2024-01-01', '2027-06-01'), day)).toBe('clad');
    expect(siteLook(site('2022-06-01', '2025-06-01'), day)).toBe('done');
  });

  it('keeps every shop of a snapshot built before the map on the Selangor high street', () => {
    expect(shopStateKey(undefined)).toBe('selangor');
    expect(shopStateKey(null)).toBe('notset');
    expect(shopStateKey('Johor')).toBe('johor');
  });
});
