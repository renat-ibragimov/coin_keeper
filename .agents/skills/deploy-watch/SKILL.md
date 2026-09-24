---
name: deploy-watch
description: >
  Follow a push through CI and deployment and confirm production is healthy. Use right
  after a push to main.
---

# deploy-watch

`gh` isn't installed; the repository is public, so the GitHub API works without auth.

1. Runs for the pushed commit (poll every 30 s in the background, not in a tight loop):
   ```bash
   sha=$(git rev-parse HEAD)
   curl -s "https://api.github.com/repos/renat-ibragimov/coin_keeper/actions/runs?head_sha=$sha" \
     | python3 -c "import sys,json; [print(r['name'], r['status'], r['conclusion'], r['html_url']) for r in json.load(sys.stdin)['workflow_runs']]"
   ```
   Expect two workflows: `CI` (check → frontend-build → build → deploy → deploy-frontend)
   and `docs`.
2. A failed job: fetch its log via
   `https://api.github.com/repos/renat-ibragimov/coin_keeper/actions/runs/<id>/jobs`, find
   the failed step, report it with the relevant lines. Don't retry blindly.
3. After `CI` succeeds:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://coins.renat-ibragimov.com/api/v1/health
   curl -s "https://coins.renat-ibragimov.com/api/v1/catalog?pageSize=1" | head -c 300
   ```
   `200` and a catalog payload → report healthy, with links to the runs.
4. If the push contained a migration, suggest a read-only `SELECT` confirming the new
   schema/data (`prod-ops` skill) and ask the owner to hard-refresh (Ctrl+Shift+R) before
   checking screens.
