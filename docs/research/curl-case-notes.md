# curl CVE-2023-38545 — case research notes

Working notes for the Incident Postmortem Generator eval case.
Research date: 2026-09-15. All facts below come from the fetched sources archived in
`data/ground_truth/` (advisory.md, blog.md, github-api.json).

## Full SHAs (resolved via GitHub commits API)

- Introducer: `4a4b63daaa01ef59b131d91e8e6e6dfe275c0f08` (short `4a4b63daaa`, 40 chars verified)
  - Subject: "socks: make the connect phase non-blocking"
  - Author: Daniel Stenberg `<daniel@haxx.se>`, author date 2020-02-14T15:16:54Z
  - Committer: Daniel Stenberg, committer date 2020-02-16T23:08:48Z (pushed to master 2 days after authoring)
  - Message body: "Removes two entries from KNOWN_BUGS.\n\nCloses #4907"
  - GPG-signed, verification.verified = true
  - Diff: 13 files, +817/−553 (total 1370). Files: docs/KNOWN_BUGS, docs/TODO, lib/connect.c,
    lib/ftp.c, lib/hostip.c, lib/hostip.h, lib/multi.c, lib/sendf.c, lib/socks.c (+665/−467,
    the bulk), lib/socks.h, lib/socks_gssapi.c, lib/socks_sspi.c, lib/urldata.h
    (adds `enum connect_t` + `struct connstate` state machine).
- Fix: `fb4415d8aee6c1045be932a34fe6107c2f5ed147` (advisory's short form `fb4415d8aee6c1` is a 13-char prefix)
  - Subject: "socks: return error if hostname too long for remote resolve"
  - Author: **Jay Satiro** `<raysatiro@yahoo.com>` (GitHub login `jay`), author date 2023-10-11T05:34:19Z
  - Committer: **Daniel Stenberg** (`bagder`), same committer date 2023-10-11T05:34:19Z
  - Message body cites the advisory: "Bug: https://curl.se/docs/CVE-2023-38545.html"
  - Diff: 3 files, +69/−5 (total 74):
    - `lib/socks.c` (+4/−4): replaces the silent `socks5_resolve_local = TRUE;` switch with
      `failf(...); return CURLPX_LONG_HOSTNAME;` for hostname_len > 255 in remote-resolve mode;
      also `(char) hostname_len` → `(unsigned char) hostname_len`.
    - `tests/data/Makefile.inc` (+1/−1): registers test728.
    - `tests/data/test728` (new, +64): "SOCKS5h with HTTP redirect to hostname too long",
      expects error code 97 (CURLE_PROXY).

## Releases

- Introduced-in: curl **7.69.0**, released **2020-03-04**
  (GitHub release `curl-7_69_0` published_at 2020-03-04T06:48:56Z; corroborated by
  https://curl.se/docs/releases.html row "218 | 7.69.0 | Mar 4 2020"; blog: "It shipped in
  7.69.0 as the first release featuring this enhancement. And by extension also the first
  release vulnerable to CVE-2023-38545.")
- Last affected: 8.3.0 (2023-09-13, per curl.se releases table; advisory: "Affected versions:
  libcurl 7.69.0 to and including 8.3.0").
- Fixed-in: curl **8.4.0**, released **2023-10-11** (advisory: "libcurl 8.4.0 was released on
  October 11 2023, coordinated with the publication of this advisory."; GitHub release
  `curl-8_4_0` published_at 2023-10-11T06:28:45Z).

## Issue #4907

- It is a **pull request**, not a plain issue: html_url https://github.com/curl/curl/pull/4907
- Title: "socks: make the connect phase non-blocking" (same as the commit subject)
- Filed by **bagder** (Daniel Stenberg), created 2020-02-11T06:38:35Z
- State: **closed, locked** (lock reason "resolved"); label "connecting & proxies"
- `pull_request.merged_at` is **null** — closed unmerged; the change landed via direct commit
  `4a4b63daaa` pushed to master, whose "Closes #4907" message closed the PR
  (PR closed_at 2020-02-16T23:09:09Z, 21s after the commit's committer date).
- Body: "Removes two entries from KNOWN_BUGS."
- Comments: 0 (issues/4907/comments returns `[]`).

## Fix PR number

**None found.** `GET /repos/curl/curl/commits/fb4415d8aee6c1/pulls` returns `[]` — the fix
commit is not associated with any pull request; it was committed directly to master
(author jay, committer bagder). Ground truth accordingly has no fix PR.

## Detection story (from advisory + blog)

- Reported by **Jay Satiro**, privately via **HackerOne report 2187833**
  (advisory links it; credits "Reported-by: Jay Satiro", "Patched-by: Jay Satiro").
- Advisory timeline: "This issue was reported to the curl project on September 30, 2023.
  We contacted distros@openwall on October 3, 2023."
- Blog: "This issue was reported, analyzed and patched by Jay Satiro." and "To learn how this
  flaw was reported and we worked on the issue before it was made public. Go check the
  Hackerone report." — the *method* of discovery is not described in our sources.
- Bounty: "This is the largest curl bug-bounty paid to date: 4,660 USD (plus 1,165 USD to the
  curl project, as per IBB policy)".

## "1315 days" arithmetic check

Blog: "the flaw then remained undiscovered in code for 1315 days". Computed endpoints:

- 2020-02-14 (commit author date) → 2023-10-11 (disclosure/fix): **1335 days**
- 2020-02-14 → 2023-09-30 (report): **1324 days**
- 2020-03-04 (7.69.0 release) → 2023-10-11: **1316 days**
- 2020-02-14 + 1315 days = 2023-09-21

None matches 1315 exactly; closest is release-to-fix at 1316. The blog does not define its
endpoints. Ground truth stores the quoted **1315** (author's own figure), not a computed one.

## Surprising findings

1. **The introducer author is also the postmortem author and the fix committer.** Daniel
   Stenberg wrote the bug (2020), wrote the blog postmortem (2023), and committed (as
   committer) Jay Satiro's fix. The fix's *author* is Jay Satiro — so `git blame` on the fix
   attributes it to the reporter, while the introducer is the maintainer himself.
2. Issue #4907 looks like an issue number but is a PR, and was **closed unmerged** — a
   generator that assumes "closes #N ⇒ PR N merged" would be wrong here.
3. The fix commit has **no associated PR** (`/pulls` → `[]`); PR-based fix detection fails on
   this case. The commit message links the *advisory URL*, not an issue.
4. The one-line root cause lived in a 1,132-line rewrite of lib/socks.c inside a 13-file
   refactor; the fix itself is 4 changed lines in lib/socks.c plus a regression test.
5. Advisory contains **no CVSS score/vector** — curl publishes only "Severity: High"
   (CWE-122: Heap-based Buffer Overflow). `severity.cvss` is null for this reason.
6. Advisory has a post-publication addendum: researcher RyotaK showed that even with a large
   buffer, an integer overflow of hostname length + crafted >255-char hostname can complete
   the handshake (impact limited; no control chars/NUL allowed in hostname).
7. GitHub release published_at for 7.69.0 (2020-03-04) matches curl.se's official table, so
   the "GitHub assets early" concern did not materialize for this case.

## Could NOT verify from fetched sources (left null or noted)

- `severity.cvss`: null — no CVSS score/vector published in the advisory.
- Exact discovery *method* (what Jay Satiro was doing when he found it): not in advisory or
  blog; both point to the (login-required) HackerOne report 2187833.
- Fix PR number: none exists per the API.
- The precise endpoints behind the blog's "1315 days" figure (see above).
- CVSS from NVD: not fetched (out of scope per source list).

## Provenance / method

- Web pages fetched 2026-09-15 with `mcp__fetch__fetch` (advisory, blog, curl.se releases
  table, 7.69.0 changelog stub).
- api.github.com read via `mcp__fetch__fetch` (7 requests, within the ≤10 unauthenticated
  budget: 2 commits, 1 issue, 1 issue-comments, 1 commit-pulls, 2 release-tags). For
  byte-exact materialization into `github-api.json`, responses were re-captured with the
  authenticated `gh api` CLI (permitted fallback; product-data collection) and
  programmatically deep-compared against the MCP-fetched introducer payload — identical.
  One hand-transcription attempt of the fix-commit JSON was discarded after the PGP
  signature block could not be verified character-for-character; `gh api` capture removed
  that risk. All key fields (SHAs, dates, messages, file lists, stats, release dates) were
  asserted equal to the MCP-fetched values by the validation script.
