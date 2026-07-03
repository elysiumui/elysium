# Launch checklist — COMPLETED (historical)

**Launch is done (2026-07-03).** Every step in the original checklist was
completed: PyLocket serves the signed Designer trial, `pip install
elysium-ui` is live on PyPI, the site serves at elysiumui.com, docs at
docs./designer.elysiumui.com, and support@elysiumui.com works.

**The living document is now [OPERATIONS.md](OPERATIONS.md)** — repo
topology, deployment paths, publish procedures, secrets, DNS, and the
current open items (§11). Update that file, not this one.

Notes vs. the original checklist (details that changed during execution):

- Trial is **14 days** (not 30) and uses **one** PyLocket URL for all OSes.
- Designer shipped as **v1.0.0** (versioned independently of the framework).
- PyLocket artifacts became fully **raw runnable builds** (`.app.zip`,
  onefile ELF, onefile exe) — the "-pylocket.zip onedir" naming is obsolete.
- `FRAMEWORK_REPO_TOKEN` is no longer used (the Designer CI checks out the
  now-public framework repo tokenless); the secret can be deleted.
- The Cloudflare Pages **git-connection path is dead** (Pages can't re-point
  a connected repo). The site deploys by **wrangler direct upload** from the
  private monorepo's `website.yml` — see OPERATIONS.md §6.
