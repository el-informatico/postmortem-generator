# Ground truth data — provenance & copyright

These files are the **human ground truth** the evaluation harness (piece 4) compares
against, for the real case curl CVE-2023-38545. They are cached copies of public web
pages, fetched 2026-09-15 for **reproducible offline evaluation**:

| File | Source | Copyright |
|---|---|---|
| `advisory.md` | https://curl.se/docs/CVE-2023-38545.html | curl project / Daniel Stenberg |
| `blog.md` | https://daniel.haxx.se/blog/2023/10/11/how-i-made-a-heap-overflow-in-curl/ | Daniel Stenberg |
| `github-api.json` | api.github.com responses (see keys inside) | GitHub API terms / respective authors |
| `ground_truth.json` | structured extraction of the above (quote-faithful; every field carries its source) | derived |

The source URLs are authoritative; the cached copies are for evaluation reproducibility
only and are not redistributed as original content. The system itself never uses these
files to *generate* postmortems — only to *evaluate* them.
