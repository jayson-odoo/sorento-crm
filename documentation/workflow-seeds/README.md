# Workflow form seeds

## Annual Dinner Sponsorship (`annual_dinner_sponsorship_form.json`)

Derived from the PDF **top half only** (customer block, criteria/SKU grid, contact, dealer dinner checkbox). The repeated block in the PDF is ignored.

### Database seed (recommended)

Run Alembic from `sorento_crm_backend`:

```bash
alembic upgrade head
```

Migration **`108_seed_annual_dinner_sponsorship_workflow`** inserts:

- Workflow definition **`annual_dinner_sponsorship`** with **draft + published** schema (states, transitions, header sections).
- One **demo submission** in **`draft`** with `sample_header_data` pre-filled.

If the definition already exists (same `code`), the migration **skips** inserts (idempotent).

### Manual import (alternative)

1. **Workflow Forms → Definitions → New workflow form**  
 - Code: `annual_dinner_sponsorship` (or copy from JSON `definition.code`)  
 - Name / description: copy from `definition` in the JSON file.

2. Open the definition → **Builder** → replace draft content by pasting **`draft_schema`** from the JSON (or merge sections manually).

3. **Publish** the form.

4. **New submission** - paste **`sample_header_data`** into the API payload field `header_data` when creating via API, or fill the form in the UI using the same values keyed by field id (`f001` … `f015`).

### Field map (quick reference)

| Id   | PDF meaning |
|------|-------------|
| f001 | Date |
| f002 | Salesman name |
| f003 | Company name |
| f004 | Delivery address |
| f005 | Payment terms band (30/60/90 / payment up to date) |
| f006 | Cat A/B mirror SKUs |
| f007 | Cat C/D faucet SKUs |
| f008 | Extra bidet/faucet (payment up to date row) |
| f009 | Annual sales ≥ RM100k |
| f010 | Approved by (office) |
| f011 | Sales manager |
| f012 | Contact person |
| f013 | Contact no |
| f014 | Delivery / pick up date |
| f015 | Dealer annual dinner - Sorento Sdn Bhd |

Adjust labels/options if your commercial rules differ from the PDF wording.
