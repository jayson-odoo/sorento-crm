# UAC: AI extract shows the real AI error (AI-EXTRACT-502)

- AC-1: When the AI provider fails during any AI extract (portal, my-requests, master-data field
  extract, project register), the API answers 503 with a JSON body, never 502.
- AC-2 (owner ruling 2 Nov, replaces the first draft): every route shows a plain message, never the
  provider's raw error; provider busy/failed: "Could not read the file just now, please try again."
  The raw error goes to the server log only.
- AC-3: The provider call is given a 45 s timeout and no SDK retries; a call that runs out answers 503
  with "The AI reader did not answer within 45 seconds" wording, within a few seconds of 45 s.
- AC-4: An empty or non-JSON provider answer answers 503 (not 502) with the plain message.
- AC-5: With no AI assistant config row and no per-form provider label, the extract answers 400
  "No AI provider is set" and never calls OpenAI.
- AC-6: Successful extracts are unchanged.
- AC-7: The extract asks for 16384 answer tokens, so a file whose line list overran the old 4096
  budget (production: 6138 answer tokens) reads.
- AC-8: An answer still cut off at the cap answers 503 "This file is too long to read in one go; try
  fewer pages."
- AC-9: A price tag, purchase or sponsorship upload of more than 6 pages is read as at most 4 page groups at once, each with its own 45 s cap and
  answer budget; the whole read ends inside one call's cap (one wave).
- AC-10: Rows come back in page order whatever order the groups finish in; an exact duplicate of an
  earlier group's row is dropped (repeats inside one group stay); a list field combines every
  group's entries.
- AC-11: When some groups fail, the rows from the others come back with a plain note naming the
  pages that were not read ("Pages 7-9 could not be read, try them again."), shown in the dialog;
  never the provider's text. When every group fails, the 503 path answers.
- AC-12: An upload of up to 6 pages, a video, any complaint (however many photos) and any form
  without line items are still read in one call.
