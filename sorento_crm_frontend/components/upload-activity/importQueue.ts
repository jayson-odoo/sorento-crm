/**
 * What a queued import route answers with.
 *
 * Every `apply`/`import` endpoint on the shared import machinery returns the same 202 body:
 * a message, the import-job id the drawer and `/system-management/import-jobs/{job_id}` key
 * on, and the row id. Declared once so the five SCM channels cannot each invent a slightly
 * different name for the same field.
 */
export interface ImportQueuedResult {
  message: string;
  /** The import-job id. What the drawer polls and what the job page is addressed by. */
  job_id: string;
  /** The `import_jobs` row id. */
  id: string;
}

/**
 * What the channel itself did is NOT typed here, on purpose.
 *
 * It lands on the job as `result.upload` - the counts, the SO/PO links a purchase upload
 * resolved, the agents an order book created - and the job page renders that object
 * generically, the same way it renders every other importer's. The per-channel result
 * interfaces that used to sit in the SCM services described that object and had no consumer
 * at all, so they were four descriptions of a response no route returns and nothing checks.
 * If a screen ever needs to read one field of it, type that field where it is read.
 */
