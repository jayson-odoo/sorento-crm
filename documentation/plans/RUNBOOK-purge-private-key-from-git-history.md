# RUNBOOK — Purge private_key.pem from git history + rotate CloudFront key

**Why:** `sorento_crm_backend/private_key.pem` (real CloudFront signing key, key-pair-id `K1NX8MQAUJBE7N`, distribution `d1k6bbzmejl1no.cloudfront.net`) was committed to git (first in `a0060d280`). Anyone who has ever cloned/forked the repo can extract it from history and forge signed CloudFront URLs.

**Status:** The file is now `git rm --cached` + gitignored on branch `security/audit-hardening-20260629` (stops *future* tracking). History still contains it until purged below.

## Step 0 — ROTATE FIRST (most important, do before/independent of git work)
The committed key is compromised regardless of history rewrite. In AWS:
1. Create a NEW CloudFront public/private key pair + key group.
2. Update the distribution's trusted key group to the new key.
3. Deploy the new private key to prod via the secret path (NOT git): set `CLOUDFRONT_PRIVATE_KEY_PATH` / key-pair-id (`K1NX8MQAUJBE7N` → new id) in the prod `.env` / secrets manager.
4. Disable/delete the old key pair once traffic confirms the new one signs correctly.

> After rotation the old leaked key is useless even if it stays in history — so Step 0 is the real fix; the history purge is hygiene.

## Step 1 — Purge from history (rewrites history; needs coordination)
**⚠️ This rewrites every commit touching the file and requires a force-push. Coordinate with the team — everyone must re-clone or hard-reset afterwards.** Do this when teammates are not mid-work.

Using git-filter-repo (preferred):
```bash
pip install git-filter-repo
cd <repo>
git filter-repo --path sorento_crm_backend/private_key.pem --invert-paths
```
Or BFG:
```bash
bfg --delete-files private_key.pem
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

## Step 2 — Force-push (DESTRUCTIVE — author's go-ahead required)
```bash
git push origin --force --all
git push origin --force --tags
```
Then notify the team to re-clone (old clones still hold the secret).

## Step 3 — Verify
```bash
git log --all --oneline -- sorento_crm_backend/private_key.pem   # expect: empty
```

## Notes
- Claude did Steps for the local un-track + gitignore only. **Steps 0–2 are intentionally left for you** because they touch AWS and rewrite shared history / force-push.
- Confirm prod's `private_key.pem` is delivered via deploy/secret path (prod has no git repo per project note) — verify the new key lands there.
