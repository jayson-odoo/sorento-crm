# UAC: AI Assistant Prompts on the standard views (AI-PROMPTS-STD-VIEWS)

List (System > AI Assistant > Prompts)
- AC-1 The list is the standard DataGrid: search, Filters, Columns, Export, Refresh, pagination.
- AC-2 Every column (Prompt, Role, Status, Runs on, Production, Latest, Last edited, Edited by)
  sorts on the server, both directions.
- AC-3 Status and Runs on filters are multi-select; several values OR together.
- AC-4 Dates read dd/mm/yyyy.
- AC-5 Rows can be ticked (select column) and the whole row opens the prompt.
- AC-6 The "Domain block out of date" banner still shows above the list when the parser is stale.
- AC-7 Dormant prompts show a Dormant pill (with the milestone) and are filterable.

Detail
- AC-8 Back to prompts returns to the same page, sort, search and filters.
- AC-9 The record header carries prev/next across the list page; it is still there after Save
  and after Publish.
- AC-10 The page opens read-only; Edit starts an edit session with Cancel + Save as new version;
  Cancel discards; Save needs a commit message and writes a NEW version.
- AC-11 The gear publishes / stages the version loaded in the editor; publishing moves the
  production label.
- AC-12 Tabs, in order: Prompt, Versions, Model, Dry run. Versions is a grid of every version
  with labels, message, author and date; clicking a row loads it into the editor.
- AC-13 The model the prompt runs on is shown and editable on the Model tab.
