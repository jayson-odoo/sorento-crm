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
