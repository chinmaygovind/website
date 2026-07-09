---
name: push
description: Ship this website to production (cgovind.com). Use whenever the user says "push", "deploy", "ship it", or otherwise wants the current changes live. Commits the working tree, pushes to main, watches the GitHub Actions deploy, and verifies the live site.
---

# Push / deploy the website

"Push" means: commit the working tree, push to `main`, let the `Deploy` GitHub
Action ship it, then verify it is live. Do all of this end to end when the user
says "push", without stopping to ask again.

## Steps

1. **Check the diff.** Run `git status --short` and `git --no-pager diff`. Make
   sure nothing secret is staged (`.env` is gitignored; keep it that way).

2. **Commit.** Stage everything and write a human-sounding message:
   - Imperative subject, short body only if it adds something.
   - No em-dashes anywhere. The user cares about this.
   - End with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
   ```bash
   git add -A
   git commit -F - <<'MSG'
   <subject line>

   <optional short body>

   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   MSG
   ```

3. **Push.** `git push origin main`.

4. **Watch the deploy.** The push triggers `.github/workflows/deploy.yml` (an
   import check, then an SSH deploy to the EC2 box).
   ```bash
   RID=$(gh run list --workflow=deploy.yml --branch main --limit 1 --json databaseId -q '.[0].databaseId')
   gh run watch "$RID" --exit-status --interval 10
   ```

5. **Verify live.** The box is at the Elastic IP `54.157.20.148`. The apex can
   negative-cache locally, so pin it and spot-check whatever changed (title, a
   new asset, the `/ttr` redirect):
   ```bash
   curl -sS --resolve cgovind.com:443:54.157.20.148 -o /dev/null -w '%{http_code}\n' https://cgovind.com/
   ```

## What the deploy does and does not do

The Action only runs `git reset --hard origin/main`, `git submodule update`,
`pip install -r requirements.txt`, and `sudo systemctl restart website`. So it
ships everything under `site/` and `app.py`, but it does NOT touch nginx, TLS
(certbot), or the box's `.env`, and it does NOT run `deploy/setup.sh`.

If you changed `deploy/nginx.conf`, the box `.env`, or anything TLS related,
apply it by hand over SSH: `ssh ubuntu@54.157.20.148`, nginx config lives at
`/etc/nginx/sites-available/website`, then `sudo nginx -t && sudo systemctl reload nginx`.

## Known failure: SSH dial timeout

If the SSH deploy step fails with `dial tcp ***:22: i/o timeout`, the `EC2_HOST`
repo secret points at a dead IP (this happened once when the box's IP moved to
the Elastic IP). Fix it and re-run just the failed job:
```bash
gh secret set EC2_HOST --body 54.157.20.148
gh run rerun <run-id> --failed
```
The deploy also relies on the `EC2_USER` and `EC2_SSH_KEY` repo secrets.
