"""TOWN-PROJECT-CITY mock v2, patch 3: with north up, Selangor's dealers face the camera (near arc), the warehouses and
the approvals office move to the far side beside the depot and the Perak causeway."""
import sys
p = sys.argv[1]
t = open(p).read()


def rep(old, new, count=1):
    global t
    n = t.count(old)
    assert n == count, (n, old[:90])
    t = t.replace(old, new)


rep("  const A0 = -60;\n  const A1 = 30;", "  const A0 = 104;\n  const A1 = 214;")
rep("const WHP = [[14.6, 160], [14.6, 181], [14.6, 202], [24.0, 166], [24.0, 187], [24.0, 208]];",
    "const WHP = [[14.6, 318], [14.6, 339], [14.6, 0], [24.0, 324], [24.0, 345], [24.0, 6]];")
rep("const [ofx, ofz] = polar(15.2, 128);", "const [ofx, ofz] = polar(15.2, 296);")
rep("office.rotation.y = faceOut(128);", "office.rotation.y = faceOut(296);")
rep("[ofx, ofz, faceOut(128), 4.9, 4.2]", "[ofx, ofz, faceOut(296), 4.9, 4.2]")
rep("  for (let a = 112; a < 296; a += 12) if (![110, 200, 232, 257, 287].some((d) => Math.abs(a - d) < 6)) lampAt.push(a);",
    "  for (let a = 226; a < 410; a += 12) if (![232, 257, 287, 380, 404].some((d) => Math.abs(a - d) < 6)) lampAt.push(a % 360);")
rep("    const [x, z] = polar(HS, 22);\n    addLabel({ text: `+${count(others)} more bought today`",
    "    const [x, z] = polar(HS, 222);\n    addLabel({ text: `+${count(others)} more bought today`")
# the sea takes no shadows: with the sun following the camera over the whole map, low shadows speckled the swell
rep("mesh(seaGeo, seaMat, { cast: false })", "mesh(seaGeo, seaMat, { cast: false, receive: false })")
open(p, 'w').write(t)
print('patch3 ok')
