"""Render the owner review page from seed/review.json.

usage: python3 make_review.py REVIEW_JSON QUESTIONS_JSON OUT_HTML
"""
import html
import json
import sys
from collections import Counter

review = json.load(open(sys.argv[1]))
questions = json.load(open(sys.argv[2]))
out_path = sys.argv[3]
E = lambda s: html.escape("" if s is None else str(s))
FAM = {"bathtub": "Bathtub", "water_closet": "Water closet", "urinal": "Urinal", "bathroom_furniture":
       "Bathroom furniture", "kitchen_sink": "Kitchen sink", "basin": "Basin", "shower_fitting": "Shower fitting package", "other": "Other"}


def money(v):
    if v is None or v == "":
        return '<span class="muted">blank</span>'
    try:
        return f"RM {float(v):,.2f}".replace(".00", "")
    except ValueError:
        return E(v)


def state_pill(state):
    cls = {"ok": "ok", "UNMATCHED": "bad", "discontinued": "warn"}.get(state, "warn")
    label = {"ok": "in catalogue", "UNMATCHED": "UNMATCHED", "discontinued": "discontinued"}.get(state, state)
    return f'<span class="pill {cls}">{E(label)}</span>'


combos = review["combos"]
fams = Counter(c.get("family") or "other" for c in combos)
n_unmatched = sum(1 for c in combos if c["unmatched"])
n_same = sum(1 for c in combos if c["existing_same"])
n_other = sum(1 for c in combos if c["existing_other"] and not c["existing_same"])
all_unmatched = Counter(u for c in combos for u in c["unmatched"])

cards = []
for c in combos:
    fam = c.get("family") or "other"
    flags = []
    if c["unmatched"]:
        flags.append('<span class="pill bad">UNMATCHED</span>')
    if c["existing_same"]:
        flags.append('<span class="pill info">already on dev (same name)</span>')
    elif c["existing_other"]:
        flags.append('<span class="pill warn">host has other combos on dev</span>')
    if not c["unmatched"] and not c["existing_same"]:
        flags.append('<span class="pill ok">new</span>')
    rows = []
    for p in c["components"]:
        rows.append(f"<tr><td>Fixed part</td><td><code>{E(p['code'])}</code></td><td>{E(p['role'])}</td>"
                    f"<td></td><td>{state_pill(c['states'].get(p['code']))}</td></tr>")
    for g in c["choice_groups"]:
        for o in g["options"]:
            rows.append(f"<tr><td>Choice: {E(g['role'])}</td><td><code>{E(o['code'])}</code></td><td></td>"
                        f"<td>{'SP ' + money(o.get('sp')) if o.get('sp') is not None else ''}</td>"
                        f"<td>{state_pill(c['states'].get(o['code']))}</td></tr>")
    for t in c["topups"]:
        rows.append(f"<tr><td>Upgrade</td><td><code>{E(t['code'])}</code></td><td>{E(t.get('descr'))}</td>"
                    f"<td>top up {money(t.get('topup'))}</td><td>{state_pill(c['states'].get(t['code']))}</td></tr>")
    for f in c["free_items"]:
        if f["kind"] == "product":
            key, what = f["code"] or f["label"], f'<code>{E(f["code"])}</code>'
            kind = "Free item (catalogue product)"
        else:
            key, what = "acc:" + f["label"], E(f["label"])
            kind = "Free item (accessory library)"
        rows.append(f"<tr><td>{kind}</td><td>{what}</td><td>{E(f['label'] if f['kind']=='product' else '')}</td>"
                    f"<td>{E(f.get('note'))}</td><td>{state_pill(c['states'].get(key))}</td></tr>")
    table = ("<table><thead><tr><th>Line</th><th>Code / name</th><th>Role / label</th><th>Price / note</th>"
             "<th>Catalogue</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>") if rows else \
        '<p class="muted">No parts, options or free items.</p>'
    existing = ""
    if c["existing_same"] or c["existing_other"]:
        items = []
        for e in c["existing_same"] + c["existing_other"]:
            same = e in c["existing_same"]
            items.append(
                f"<li>{'<strong>same name</strong>: ' if same else ''}\"{E(e['name'])}\" (created {E(e['created'])}; "
                f"LP {money(e['lp'])}, SP {money(e['sp'])}, description {'set' if e['has_description'] else 'empty'}, "
                f"{e['parts']} parts, {e['free']} free items)</li>")
        existing = f'<div class="existing"><h4>On the dev copy (4 Nov) for this host</h4><ul>{"".join(items)}</ul></div>'
    lps = ""
    if c.get("printed_lps"):
        lps = "<div class='muted small'>Printed LPs: " + ", ".join(
            f"{E(x.get('code'))} {money(x.get('lp'))}" for x in c["printed_lps"]) + "</div>"
    unsure = f'<div class="unsure"><strong>Reader note:</strong> {E(c["unsure"])}</div>' if c.get("unsure") else ""
    host_name = E(c.get("host_name")) if c.get("host_name") else '<span class="pill bad">host not in catalogue</span>'
    search = " ".join([c["host_code"], c["combo_name"], *(p["code"] for p in c["components"]),
                       *c["unmatched"]]).lower()
    cards.append(f"""
<article class="card" data-fam="{E(fam)}" data-unmatched="{1 if c['unmatched'] else 0}"
  data-exists="{1 if (c['existing_same'] or c['existing_other']) else 0}" data-q="{E(search)}">
  <header><div><span class="page">p{c['page']}</span> <span class="fam">{E(FAM.get(fam, fam))}</span>
  <span class="muted small">{E(c.get('heading'))}</span></div><div>{' '.join(flags)}</div></header>
  <h3>{E(c['combo_name'])}</h3>
  <div class="host">Host <code>{E(c['host_code'])}</code> {host_name}</div>
  <div class="prices"><div><span>List price</span><b>{money(c.get('lp'))}</b></div>
  <div><span>Selling price</span><b>{money(c.get('sp'))}</b></div>
  <div><span>IV (info, not seeded)</span><b>{money(c.get('iv'))}</b></div></div>{lps}
  <div class="desc"><div class="label">Description (as stored, bold as printed)</div>{c['combo_description'] or '<p class="muted">none</p>'}</div>
  {table}{existing}{unsure}
</article>""")

not_combo_rows = "".join(
    f"<tr><td>p{E(n.get('page'))}</td><td><code>{E(n.get('code') or '')}</code></td><td>{E(n.get('reason'))}</td></tr>"
    for n in sorted(review["not_combos"], key=lambda n: (n.get("page") or 0, n.get("code") or "")))
offer_rows = "".join(
    f"<tr><td>p{E(o.get('page'))}</td><td>{E(o.get('text'))}</td></tr>"
    for o in sorted(review["page_offers"], key=lambda o: o.get("page") or 0))
unmatched_rows = "".join(
    f"<tr><td><code>{E(u)}</code></td><td>{n}</td><td>"
    + ", ".join(E(c['id']) for c in combos if u in c['unmatched']) + "</td><td>"
    + (", ".join(E(h) for h in review.get("hints", {}).get(u, [])) or '<span class="muted">none</span>')
    + "</td></tr>"
    for u, n in sorted(all_unmatched.items()))
q_html = "".join(
    f"<li><p><strong>{E(q['id'])}. {E(q['question'])}</strong></p><ul>"
    + "".join(f"<li>{E(o)}</li>" for o in q["options"])
    + f"</ul><p class='rec'>Recommendation: {E(q['recommendation'])}</p></li>" for q in questions)
fam_opts = "".join(f'<option value="{E(k)}">{E(FAM.get(k, k))} ({v})</option>' for k, v in sorted(fams.items()))

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flyer Combo Seed Review</title>
<style>
:root {{ --bg:#f6f7f5; --card:#fff; --ink:#1f2421; --muted:#6b7280; --line:#e3e6e1; --brand:#435236;
  --ok:#1f7a3a; --okbg:#e6f4ea; --bad:#b42318; --badbg:#fde8e7; --warn:#8a5a00; --warnbg:#fff4d6;
  --info:#1d4ed8; --infobg:#e3ecff; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#14171a; --card:#1d2125; --ink:#e7eae6;
  --muted:#9aa3ad; --line:#2d3338; --brand:#a9c38f; --ok:#7fd69a; --okbg:#173622; --bad:#ff9b92; --badbg:#3d1a17;
  --warn:#f2c46b; --warnbg:#3a2e12; --info:#9db8ff; --infobg:#1c2747; }} }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif }}
main {{ max-width:1180px; margin:0 auto; padding:24px 16px 64px }}
h1 {{ font-size:22px; margin:0 0 4px }} h2 {{ font-size:17px; margin:32px 0 10px }}
.muted {{ color:var(--muted) }} .small {{ font-size:12px }}
.summary {{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 }}
.summary div {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px 12px }}
.summary b {{ display:block; font-size:18px }}
.questions {{ list-style:none; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:4px 18px }}
.questions > li {{ margin:12px 0 }} .rec {{ color:var(--ok); margin:4px 0 }}
.filters {{ position:sticky; top:0; z-index:2; background:var(--bg); padding:10px 0; display:flex; flex-wrap:wrap;
  gap:10px; align-items:center; border-bottom:1px solid var(--line) }}
.filters input[type=search], .filters select {{ padding:6px 8px; border:1px solid var(--line); border-radius:6px;
  background:var(--card); color:var(--ink); min-width:0 }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr)); gap:14px; margin-top:14px }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; min-width:0 }}
.card header {{ display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap }}
.card h3 {{ margin:8px 0 2px; font-size:16px; overflow-wrap:anywhere }}
.page {{ background:var(--brand); color:var(--card); border-radius:4px; padding:1px 6px; font-weight:600; font-size:12px }}
.fam {{ font-weight:600; font-size:12px }}
.pill {{ display:inline-block; border-radius:999px; padding:1px 8px; font-size:11px; font-weight:600; white-space:nowrap }}
.pill.ok {{ background:var(--okbg); color:var(--ok) }} .pill.bad {{ background:var(--badbg); color:var(--bad) }}
.pill.warn {{ background:var(--warnbg); color:var(--warn) }} .pill.info {{ background:var(--infobg); color:var(--info) }}
.prices {{ display:flex; gap:18px; flex-wrap:wrap; margin:8px 0 }} .prices span {{ display:block; font-size:11px; color:var(--muted) }}
.desc {{ border-left:3px solid var(--brand); padding:4px 10px; margin:10px 0; font-size:13px }}
.desc p {{ margin:0 }} .label {{ font-size:11px; color:var(--muted); margin-bottom:4px }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; margin-top:8px; table-layout:fixed }}
th, td {{ text-align:left; border-bottom:1px solid var(--line); padding:5px 6px; vertical-align:top; overflow-wrap:anywhere }}
th {{ font-size:11px; color:var(--muted); font-weight:600 }}
.existing {{ margin-top:10px; background:var(--infobg); border-radius:8px; padding:6px 10px; font-size:12.5px }}
.existing h4 {{ margin:2px 0; font-size:12px }} .existing ul {{ margin:4px 0; padding-left:18px }}
.unsure {{ margin-top:10px; background:var(--warnbg); color:var(--ink); border-radius:8px; padding:6px 10px; font-size:12.5px }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px }}
.listbox {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; overflow-x:auto }}
@media (max-width:600px) {{ th:nth-child(3), td:nth-child(3) {{ display:none }} }}
</style></head><body><main>
<h1>Flyer combo seed: review before loading</h1>
<p class="muted">Source: "UPDATED SORENTO A3 FLYER 2026 DEALER_21072026.pdf" (promotion attachment, 71 pages), read
page by page. Codes are matched to the catalogue exactly; nothing is guessed. "On dev" means the 4 Nov copy of the
system; combos you added by hand after 4 Nov are not visible here, so the prod dry run is the final check.</p>
<div class="summary">
<div><span class="muted small">Combos found</span><b>{len(combos)}</b></div>
{''.join(f'<div><span class="muted small">{E(FAM.get(k, k))}</span><b>{v}</b></div>' for k, v in sorted(fams.items()))}
<div><span class="muted small">With an UNMATCHED code or name</span><b>{n_unmatched}</b></div>
<div><span class="muted small">Same name already on dev</span><b>{n_same}</b></div>
<div><span class="muted small">Host has other combos on dev</span><b>{n_other}</b></div>
</div>
<h2>Questions for you</h2>
<ol class="questions">{q_html}</ol>
<h2>Combos</h2>
<div class="filters">
<input type="search" id="q" placeholder="Search code or name" aria-label="Search code or name">
<select id="fam" aria-label="Family"><option value="">All families</option>{fam_opts}</select>
<label><input type="checkbox" id="um"> Only UNMATCHED</label>
<label><input type="checkbox" id="ex"> Only already on dev</label>
<span class="muted small" id="count"></span>
</div>
<div class="grid" id="grid">{''.join(cards)}</div>
<h2>UNMATCHED codes and names ({len(all_unmatched)})</h2>
<div class="listbox"><table><thead><tr><th>Code / name as printed</th><th>Combos</th><th>Which (id = page-tile)</th><th>Catalogue codes that start the same (hint only, never used)</th></tr></thead>
<tbody>{unmatched_rows}</tbody></table></div>
<h2>Not combos (single products, left out)</h2>
<div class="listbox"><table><thead><tr><th>Page</th><th>Code</th><th>Why</th></tr></thead><tbody>{not_combo_rows}</tbody></table></div>
<h2>Page-wide offers (not tied to one combo, left out)</h2>
<div class="listbox"><table><thead><tr><th>Page</th><th>As printed</th></tr></thead><tbody>{offer_rows}</tbody></table></div>
</main>
<script>
const q=document.getElementById('q'),fam=document.getElementById('fam'),um=document.getElementById('um'),
ex=document.getElementById('ex'),count=document.getElementById('count'),cards=[...document.querySelectorAll('.card')];
function run(){{const t=q.value.trim().toLowerCase();let n=0;for(const c of cards){{const ok=(!t||c.dataset.q.includes(t))
&&(!fam.value||c.dataset.fam===fam.value)&&(!um.checked||c.dataset.unmatched==='1')&&(!ex.checked||c.dataset.exists==='1');
c.style.display=ok?'':'none';if(ok)n++;}}count.textContent=n+' shown';}}
[q,fam,um,ex].forEach(e=>e.addEventListener('input',run));run();
</script></body></html>"""
open(out_path, "w").write(page)
print("wrote", out_path, len(page) // 1024, "KB")
