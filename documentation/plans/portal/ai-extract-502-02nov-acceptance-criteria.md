# UAC: AI extract shows the real AI error (AI-EXTRACT-502)

- AC-1: When the AI provider fails during any AI extract (portal, my-requests, master-data field
  extract, project register), the API answers 503 with a JSON body, never 502.
- AC-2: Portal, my-requests and master-data: the JSON `message` carries the provider's own error text,
  so the AI Extract dialog shows it. Project register keeps its plain "could not be reached" message.
- AC-3: The provider call is given a 45 s timeout and no SDK retries; a call that runs out answers 503
  with "The AI reader did not answer within 45 seconds" wording, within a few seconds of 45 s.
- AC-4: An empty or non-JSON provider answer answers 503 (not 502).
- AC-5: With no AI assistant config row and no per-form provider label, the extract answers 400
  "No AI provider is set" and never calls OpenAI.
- AC-6: Successful extracts are unchanged.
