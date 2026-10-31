# Embeddings - check and fill the search vectors

Use this page to see whether the CRM's "smart search" is ready: the chatbot and the AI assistant
match words like a brand nickname or a misspelt category to the right record by comparing
**vectors** (embeddings). A row with no vector cannot be found that way. From here you can test a
phrase and fill in missing vectors.

## Where to find it

**System > Configuration > Embeddings** (`/system-management/embeddings`). Page header:
**Embeddings**. You need **View Lookup Sets** to open it.

## The summary strip

* **Embedder**: the model that makes the vectors.
* **Lookup words with a vector**: how many lookup words have one, out of how many.
* **Record chunks, new model** (Lookup words tab) or **Records left to embed** (Records tab).
* **Record search reads**: which model record search uses now. A badge says **Ready to switch**,
  or **{model} in progress** while records are still being moved to a new model.

## Lookup words tab

The words the bot resolves names against (category, file type, sales channel, spec, brand,
promotion kind, location, salesperson, customer), one sub-tab each. Columns: **Row**,
**Source**, **Words matched on**, **Vectors**. A dot reads *Vector stored* or *No vector yet*.

* **Embed missing** (needs **Edit Lookup Sets**) makes vectors for every word that has none.
  You see *Embedding started*; the counts fill in over the next minutes.
* **Try a phrase**: type a phrase (*Type a phrase*) and click **Try**. You get a verdict (for
  example Resolved or Ambiguous) and the rows that came near, with **Row**, **Spelling**,
  **Vector**, **Partial** and **Result** (**Pass** / **Fail**). *No rows came near* means nothing
  matched; add the word to the right lookup set.

## Records tab

How many business records (products, orders and so on) have vectors, per source. Columns:
**Source**, **Documents**, one column for the model search uses now, one for the new model (only
when they differ), and **Coverage %** (green at 100%).

* **Start backfill** fills in records that have no vector (*Backfill started*). **Stop** shows
  while it runs (*Backfill stopping*).
* Starting or stopping a backfill is an admin action. Others get *Permission required:
  system.settings.update*.
* The tab opens in under a second and refreshes its counts every 30 seconds while it is open and
  the browser tab is visible.

## See also

* [Chatbot - "which products have X"](chatbot-attribute-set-answers.md)
* [Entity kinds](chatbot-entity-kinds.md)
* [System Management - Data reference for admins](data-analysis.md)
