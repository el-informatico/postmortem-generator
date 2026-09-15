# Ground truth — GitLab.com 2017-01-31 database outage — provenance notes

Human ground truth for the secondary *operational* case (the "incident
without code" honesty path), fetched 2026-09-15. Same conventions as the
curl case: every field carries an exact quote or verbatim API value plus its
source; unverifiable fields are null — here that includes `introducer` and
`fix` by design (see the `*_is_null_because` keys in ground_truth.json).

## Raw sources in this directory

| File | Source | What it is |
|---|---|---|
| `postmortem.md` | https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/ | the full GitLab postmortem (raw text as fetched) |
| `issue-1684.md` | gitlab.com API v4 + rendered page | remediation tracking issue #1684 (verbatim fields + description checklist) |

## Deviation from the task's stated source location (documented on purpose)

- The remediation tracking issue **#1684 lives in the `gitlab-com/infrastructure`
  project on gitlab.com**, not in `gitlab-org/gitlab` (the postmortem's own
  link is https://gitlab.com/gitlab-com/infrastructure/issues/1684). The
  project has since been moved to `gitlab-com/gl-infra/production-engineering`.
- **GitHub hosts no `gitlab-org/gitlab` repository** (404 via `gh api`), and
  the `gitlabhq/gitlabhq` mirror has issues disabled (410). Therefore this
  case's GitHub-API cache under `data/cache/` is **hand-seeded from the
  GitLab.com REST API**: the issue body/author/state/dates are verbatim from
  https://gitlab.com/api/v4/projects/gitlab-com%2Finfrastructure/issues/1684,
  mapped into the GitHub issue JSON shape the collector expects. The case
  config uses repo `gitlab-com/infrastructure` (the real project path at the
  time) and the cache entries document this mapping in their `notes` field.
  `scripts/refresh_cache.py --case` CANNOT warm this case (GitHub 404s); the
  seeded cache is committed-adjacent data, not a fetch artifact.
- The 6 discussion notes on #1684 could not be fetched (the v4 notes
  endpoint returned 401 for unauthenticated access at fetch time). The
  description alone carries the per-issue remediation status, so the
  ground truth uses only the description.

## Timezone/date conventions

The postmortem's timeline uses "± HH:MM UTC" markers. Ground-truth timeline
events keep the postmortem's date (2017-01-31 / 2017-02-01) and carry the
time marker verbatim inside the event text. The outage duration quote
("about 18 hours") and the data-loss windows are quoted verbatim — note the
postmortem itself states two windows: "between 17:20 and 00:00 UTC" (intro,
the full unrecoverable span) and "between January 31st 17:20 UTC and 23:30
UTC" (data-loss section).

## Why introducer/fix are null

The incident has no introducing code change and no fixing commit: it was a
load spike + human error during manual replication repair, remediated
through procedural/infrastructure issues (#1094-#1105 and follow-ups), all
predating/outside any single commit in the gitlab-org/gitlab codebase.
Asserting a commit sha for either role would be fabrication, so both are
null and the pipeline is expected to emit red "No evidence" for resolution
and issue-thread-derived statements elsewhere (the honesty path under test).
