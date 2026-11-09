"""Merge the per-range extraction files into the importer seed + review data, mapped against the dev DB.

usage: python3 build_seed.py SCRATCH_DIR PG_URL
Reads  SCRATCH/extract/pages-*.json
Writes SCRATCH/seed/combo_seed_flyer_2026.json  (importer seed, list)
       SCRATCH/seed/review.json                 (review page data)
Read-only against the DB (psql -At, SELECT only).
"""
import glob
import html
import json
import os
import re
import subprocess
import sys

SCR, PG = sys.argv[1], sys.argv[2]
FLYER = "UPDATED SORENTO A3 FLYER  2026 DEALER_21072026.pdf"
SRT = "00000000-0000-0000-0000-000000000001"


def q(sql):
    out = subprocess.run(["psql", PG, "-At", "-F", "\t", "-c", sql], check=True, capture_output=True, text=True).stdout
    return [line.split("\t") for line in out.splitlines() if line]


def lit(values):
    return ",".join("'" + v.replace("'", "''") + "'" for v in values) or "''"


def to_html(lines):
    out = []
    for line in lines or []:
        parts = re.split(r"(\*\*.+?\*\*)", line)
        buf = []
        for part in parts:
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                raw = part[2:-2]
                inner = raw.strip()
                if inner:
                    lead = " " if raw[:1].isspace() else ""
                    tail = " " if raw[-1:].isspace() else ""
                    buf.append(f"{lead}<strong>{html.escape(inner, quote=False)}</strong>{tail}")
            elif part:
                buf.append(html.escape(part, quote=False))
        text = re.sub(r"\s+", " ", "".join(buf)).strip()
        if text:
            out.append(f"<p>{text}</p>")
    return "".join(out)


combos, not_combos, offers = [], [], []
for path in sorted(glob.glob(os.path.join(SCR, "extract", "pages-*.json"))):
    data = json.load(open(path))
    combos += data.get("combos", [])
    not_combos += data.get("not_combos", [])
    offers += data.get("page_offers", [])
combos.sort(key=lambda c: (c["page"], c["id"]))

# ---- codes and names to map
codes, acc_names = set(), set()
for c in combos:
    codes.add((c.get("host_code") or "").upper())
    for p in c.get("components", []):
        codes.add((p.get("code") or "").upper())
    for g in c.get("choice_groups", []):
        for o in g.get("options", []):
            codes.add((o.get("code") or "").upper())
    for f in c.get("free_items", []):
        if f.get("kind") == "product" and f.get("code"):
            codes.add(f["code"].upper())
        elif f.get("kind") == "accessory":
            acc_names.add((f.get("label") or "").upper())
codes.discard("")
products = {
    r[0].upper(): {"name": r[1], "discontinued": r[2] == "t", "active": r[3] == "t", "id": r[4]}
    for r in q(
        "select product_code, product_name, coalesce(is_discontinued,false), coalesce(is_active,true), id "
        f"from products where company_id='{SRT}' and upper(product_code) in ({lit(sorted(codes))})"
    )
}
accessories = {
    r[0].upper(): r[0]
    for r in q(f"select name from accessories where company_id='{SRT}' and upper(name) in ({lit(sorted(acc_names))})")
}
hosts = sorted({(c.get("host_code") or "").upper() for c in combos} - {""})
existing = {}
for r in q(
    "select upper(p.product_code), c.name, c.list_price, c.sell_price, "
    "(c.description is not null and c.description<>''), "
    "(select count(*) from product_combo_parts x where x.combo_id=c.id), "
    "(select count(*) from product_combo_accessories a where a.combo_id=c.id), c.created_at::date "
    "from product_combos c join products p on p.id=c.host_product_id "
    f"where p.company_id='{SRT}' and upper(p.product_code) in ({lit(hosts)}) order by c.created_at"
):
    existing.setdefault(r[0], []).append(
        {"name": r[1], "lp": r[2] or None, "sp": r[3] or None, "has_description": r[4] == "t",
         "parts": int(r[5]), "free": int(r[6]), "created": r[7]}
    )

# ---- names: one joined form, and the explicit renames the review page lists (same host printed twice)
NAME_OVERRIDES = {
    # p18 prints these cabinets again as "WATER CLOSET COMBO" packages; the 2 Nov import named them so.
    "p18-01": {"combo_name": "SRTBF11416 + water closet"},
    "p18-02": {"combo_name": "SRTBF11415 + water closet"},
    "p18-03": {"combo_name": "SRTBF11707 + water closet"},
    "p18-04": {"combo_name": "SRTBF31417 + water closet"},
    # p21 repeats SRTBF11834 + SRTMR502-BL with another tap and basins; same parts as the 2 Nov "(p9)" combo.
    "p21-05": {"combo_name": "SRTBF11834 + SRTMR502-BL (p21)", "aka": ["SRTBF11834 + SRTMR502-BL (p9)"]},
    # p55 and p56 print these sinks twice; p56 (SRTKT71SS tap) is the combo already on file.
    "p55-05": {"combo_name": "SRTKS8835-BL + SRTKT74SS-BL OR SRTKT74SS-GM"},
    "p55-06": {"combo_name": "SRTKS1235-BL + SRTKT74SS-BL OR SRTKT74SS-GM"},
    "p55-07": {"combo_name": "SRTKS8835 + SRTKT74SS-GM"},
    "p55-08": {"combo_name": "SRTKS1035 + SRTKT74SS-GM"},
}
# Left out on purpose (review page question e): one product with its fittings, not a package.
LEFT_OUT = {"p12-01": "single product with included fittings (bidet seat), not a package"}
for c in [c for c in combos if c["id"] in LEFT_OUT]:
    not_combos.append({"page": c["page"], "code": c["host_code"], "reason": LEFT_OUT[c["id"]]})
combos = [c for c in combos if c["id"] not in LEFT_OUT]
for c in combos:
    if c["combo_name"].startswith("Fitting Package"):
        c["family"] = "shower_fitting"
for c in combos:
    c["combo_name"] = re.sub(r"\s*\+\s*", " + ", " ".join(c["combo_name"].split()))
    c.update(NAME_OVERRIDES.get(c["id"], {}))

# ---- build
seed, review = [], []
for c in combos:
    host = (c.get("host_code") or "").upper()
    unmatched = []

    def code_state(code):
        p = products.get((code or "").upper())
        if not code:
            return "no code"
        if p is None:
            unmatched.append(code)
            return "UNMATCHED"
        return "discontinued" if p["discontinued"] else "ok"

    host_state = code_state(host)
    components = [{"code": p["code"].upper(), "role": p.get("role") or ""} for p in c.get("components", [])]
    groups, topups = [], []
    for g in c.get("choice_groups", []):
        role = (g.get("role") or "").strip()
        opts = []
        for o in g.get("options", []):
            if o.get("upgrade"):
                topups.append({"code": o["code"].upper(), "descr": role, "topup": o.get("topup")})
            else:
                opts.append({"code": o["code"].upper(), "descr": "", "sp": o.get("sp")})
        if opts:
            groups.append({"role": role, "options": opts})
    free = []
    for f in c.get("free_items", []):
        item = {"kind": f.get("kind"), "code": (f.get("code") or "").upper(), "label": f.get("label") or "",
                "note": f.get("note") or ""}
        free.append(item)
    # A "group" of one option is not a choice. The bathtub mixer is printed in the FREE box with colour
    # top-ups beside it: the base mixer is a free item, the colours stay upgrades. Otherwise it is fixed.
    keep_groups = []
    for g in groups:
        if len(g["options"]) == 1:
            only = g["options"][0]
            free_note = next((f["note"] for f in free if "FREE" in (f["note"] or "").upper()), None)
            if topups and free_note:
                free.append({"kind": "product", "code": only["code"], "label": g["role"], "note": free_note})
            else:
                components.append({"code": only["code"], "role": g["role"]})
        else:
            keep_groups.append(g)
    groups = keep_groups
    states = {}
    for p in components:
        states[p["code"]] = code_state(p["code"])
    for g in groups:
        for o in g["options"]:
            states[o["code"]] = code_state(o["code"])
    for t in topups:
        states[t["code"]] = code_state(t["code"])
    for f in free:
        if f["kind"] == "product":
            states[f["code"] or f["label"]] = code_state(f["code"])
        else:
            label = f["label"].upper()
            if label in accessories:
                states["acc:" + f["label"]] = "ok"
            else:
                states["acc:" + f["label"]] = "UNMATCHED"
                unmatched.append(f["label"])
    desc = to_html(c.get("description_lines"))
    entry = {
        "id": c["id"], "flyer": FLYER, "page": c["page"], "host_code": host, "combo_name": c["combo_name"][:100],
        "aka": c.get("aka", []), "combo_description": desc, "components": components, "choice_groups": groups,
        "topups": topups, "free_items": free, "lp": c.get("lp"), "sp": c.get("sp"), "unsure": c.get("unsure") or "",
    }
    seed.append(entry)
    ex = existing.get(host, [])
    names = {entry["combo_name"].strip().lower(), *(a.strip().lower() for a in entry["aka"])}
    same = [e for e in ex if e["name"].strip().lower() in names]
    review.append({
        **entry, "family": c.get("family"), "heading": c.get("heading"), "iv": c.get("iv"),
        "printed_lps": c.get("printed_lps") or [], "description_lines": c.get("description_lines"),
        "host_state": host_state, "host_name": (products.get(host) or {}).get("name"),
        "states": states, "unmatched": unmatched,
        "existing_same": same, "existing_other": [e for e in ex if e not in same],
    })

os.makedirs(os.path.join(SCR, "seed"), exist_ok=True)
json.dump(seed, open(os.path.join(SCR, "seed", "combo_seed_flyer_2026.json"), "w"), indent=1, ensure_ascii=False)
json.dump({"combos": review, "not_combos": not_combos, "page_offers": offers},
          open(os.path.join(SCR, "seed", "review.json"), "w"), indent=1, ensure_ascii=False)
um = sorted({u for r in review for u in r["unmatched"]})
# Hints for the owner only (never used to load): catalogue codes that start with the printed code.
hints = {}
for code in um:
    if " " in code or not code.upper().startswith(("SRT", "FG-")):
        continue
    found = []
    for prefix in (code, code.split("-")[0], re.sub(r"[A-Z]+$", "", code.split("-")[0])):
        rows = q("select product_code || case when coalesce(is_discontinued,false) then ' (discontinued)' else '' end "
                 f"from products where company_id='{SRT}' and product_code ilike '{prefix.replace(chr(39), '')}%' "
                 "order by product_code limit 10")
        found = [r[0] for r in rows]
        if found:
            break
    hints[code] = found
rv = json.load(open(os.path.join(SCR, "seed", "review.json")))
rv["hints"] = hints
json.dump(rv, open(os.path.join(SCR, "seed", "review.json"), "w"), indent=1, ensure_ascii=False)
print(f"combos {len(seed)}; with unmatched {sum(1 for r in review if r['unmatched'])}; distinct unmatched {len(um)}")
print(f"same-name on dev {sum(1 for r in review if r['existing_same'])}; host has other combos "
      f"{sum(1 for r in review if r['existing_other'] and not r['existing_same'])}")
print("unmatched:", ", ".join(um)[:1500])
