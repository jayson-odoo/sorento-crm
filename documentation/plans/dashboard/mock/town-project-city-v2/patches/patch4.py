"""TOWN-PROJECT-CITY mock v2, patch 4: labels that suit a map (an off-screen pill hides; the whole-map view shows the
state pills only), each state's buildings centred on its street, KL a little larger."""
import sys
p = sys.argv[1]
t = open(p).read()


def rep(old, new, count=1):
    global t
    n = t.count(old)
    assert n == count, (n, old[:90])
    t = t.replace(old, new)


rep("{ key: 'kl', name: 'Kuala Lumpur', e: 44, n: 10, rx: 9.5, ry: 8.5,", "{ key: 'kl', name: 'Kuala Lumpur', e: 46, n: 11, rx: 12, ry: 9.5,")

# ---- labels: a state pill is marked; off-screen pills hide, fixed or not; zoomed out, only the state pills show
rep("interface Label {", "interface Label {\n  isState?: boolean;")
rep("""      return on || L.fixed ? { x: p.x, y: p.y - L.h / 2, w: L.w, h: L.h } : null;""",
    """      const overview = view.current.zoom < 0.45;
      if (overview && !L.isState) return null;
      return on ? { x: p.x, y: p.y - L.h / 2, w: L.w, h: L.h } : null;""")
rep("""    const fixedBoxes = fixedL.map((L) => box(L) as ScreenBox);
    const stageView = { left: 0, right: w, bottom: 0, top: h };
    const spots = separateLabels(fixedBoxes, boardBox, stageView, 6);
    const placed = [boardBox, ...fixedBoxes.map((b, i) => ({ ...b, ...spots[i] }))];""",
    """    const fixedAll = fixedL.map((L) => box(L));
    const fixedBoxes = fixedAll.filter((b): b is ScreenBox => !!b);
    const stageView = { left: 0, right: w, bottom: 0, top: h };
    const onSpots = separateLabels(fixedBoxes, boardBox, stageView, 6);
    let k = 0;
    const spots = fixedAll.map((b) => (b ? onSpots[k++] : null));
    const placed = [boardBox, ...fixedBoxes.map((b, i) => ({ ...b, ...onSpots[i] }))];""")
rep("    fixedL.forEach((L, i) => put(L, spots[i]));", "    fixedL.forEach((L, i) => put(L, spots[i] ?? null));")
rep("""        () => raw(d.name, bits.join(' · ') || 'Nothing here today'),
      );""", """        () => raw(d.name, bits.join(' · ') || 'Nothing here today'),
      );
      labels[labels.length - 1].isState = true;""")
# a zoom change crosses the overview threshold: labels must be re-laid out (placeCam already marks them dirty)

# ---- each state's content (shops, then sites, then towers) is centred on its street
rep("""  const routeTo = (st: string, along: number)""", """  const countIn = (list: { state?: string | null }[] | undefined, st: string) => (list ?? []).filter((r) => (r.state ?? 'notset') === st).length;
  const extra = snapshot as TownSnapshot & { projects?: { sites: { state: string | null }[] }; trading_houses?: { rows: { state: string | null }[] } };
  /** where a state's row of buildings starts down its street, so shops + sites + towers sit centred on it */
  const startOf = (st: string) => {
    const shops = order.filter((s) => stateOf(s) === st).length;
    const len = Math.ceil(shops / 2) * 2.9 + Math.ceil(countIn(extra.projects?.sites, st) / 2) * 3.7 + Math.ceil(countIn(extra.trading_houses?.rows, st) / 2) * 3.0 + 2.6;
    return Math.max(3.4, (streets[st].len - len) / 2);
  };
  const routeTo = (st: string, along: number)""")
rep("      const along = 4.2 + Math.floor(k / 2) * 2.9;", "      const along = startOf(st) + 0.8 + Math.floor(k / 2) * 2.9;")
rep("    const along0 = 4.2 + Math.ceil(shops / 2) * 2.9 + 0.6;", "    const along0 = startOf(st) + 0.8 + Math.ceil(shops / 2) * 2.9 + 0.6;")
rep("    const road = routeTo(st, 4.2 + Math.ceil(shops / 2) * 2.9 + 1.4);", "    const road = routeTo(st, startOf(st) + 0.8 + Math.ceil(shops / 2) * 2.9 + 1.4);")
rep("      if (off < 5.6 && along > 3 && along < S.len - 1 && (perState[i.d.key] != null || sitesBy[i.d.key] || towersBy[i.d.key]) && along < 4.2 + Math.ceil(((perState[i.d.key] ?? -1) + 1) / 2) * 2.9 + Math.ceil((sitesBy[i.d.key]?.length ?? 0) / 2) * 3.7 + Math.ceil((towersBy[i.d.key]?.length ?? 0) / 2) * 3.0 + 3) continue;",
    "      if (off < 5.8 && along > startOf(i.d.key) - 1 && along < S.len - startOf(i.d.key) + 3) continue;")
# a state view zooms in to read its buildings (the street sits on the island's centre line)
rep("    tweenTo({ zoom: clamp(24 / Math.max(d.rx, d.ry, 9), 0.55, 1.6), tilt: DEFAULT_VIEW.tilt }, 0.9, new THREE.Vector3(x, 0, z));",
    "    tweenTo({ zoom: d.rx > 30 ? 1.2 : 1.6, tilt: DEFAULT_VIEW.tilt }, 0.9, new THREE.Vector3(x, 0, z));")
open(p, 'w').write(t)
print('patch4 ok')
