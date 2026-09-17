# Hackathon status check — 2026-09-15 (afternoon re-verification)

Re-verification of the IBM Bob 2.0 hackathon (lablab.ai) status, afternoon of 2026-09-15, against the morning snapshot taken earlier the same day. All web access read-only (DDG search MCP + fetch MCP). No pages contained text addressed to an AI assistant; nothing needed to be ignored on instruction-safety grounds (one docs page ended with a "How is this topic?" feedback-widget string, treated as page furniture).

Method note: the lablab event page is client-rendered; its full content (challenge text, prizes, submission section, judging criteria, speakers, embedded event JSON) was extracted from the server-rendered Next.js/builder.io payload in the raw HTML of <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon>.

---

## 1. Registered / participant count and /live stats

Source: <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon/live> (fetched 2026-09-15 afternoon)

- "Registered builders **10,700**" — "**+227 in last 24h**"
- "Teams forming **1,742**"
- "Tech partners **0**"
- "Tracks **TBA** — Announced soon"
- Status line: "Upcoming · Registration open — starts Sep 25, 2026, 15:00 UTC"

Morning snapshot had 10,680 registered / 1,739 teams → +20 registered, +3 teams since morning (page now rounds to 10,700).

## 2. Judges, tracks, 2nd challenge

- **Tracks: still TBA.** /live shows "Tracks — TBA — Announced soon" (<https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon/live>). No track list anywhere on the main page.
- **Judges: partially published — 2 names, both lablab/NativelyAI side; no IBM judges yet.** The main page now carries a "**Speakers, Mentors & Judges**" section containing exactly two people (16 `guestName` references in the page data, all resolving to these two):
  - Pawel Czech — CEO, NativelyAI
  - Andrea Marazzi — Founder & CCO, NativelyAI

  The embedded event JSON still has `"externalRolePersons":[]` (no formal judge/role entries registered in lablab's system). The morning snapshot recorded "judges NOT published"; the section may have been populated since then or was empty this morning — either way, an IBM-side judging panel is still unpublished.
- **2nd challenge: still absent.** No second-challenge teaser on the page. The only "second" references are the edition note "🆕 Second IBM Bob Hackathon — now featuring Bob 2.0" and the details note: "Note: This is the second IBM Bob Hackathon, now running on Bob 2.0. Registration and access details will be confirmed as the event date approaches."
- Related but separate programs (do not confuse with a 2nd challenge of this event):
  - "AI Builders Challenge with IBM Bob" — BeMyApp/IBM SkillsBuild student program, July–Sept 2026, $15,000 pool, virtual conference **Sept 16, 2026** (<https://aibuilderschallenge-bob.bemyapp.com/>). Students only, team size 1–5.
  - "IBM Champions Bobathon" — Sept 28, 2026, New York (search result only; not fetched).

## 3. Bobcoins budget for September

**No September figure exists yet — still unverified.** Findings:

- The September event page contains **zero occurrences of "Bobcoin"** (checked the full decoded page). Technology access section says only: "Participants will receive access to IBM Bob 2.0 at the start of the hackathon." and "⏳ **Access details TBA**" (<https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon>).
- May edition (reference figure): the May guide PDF states "For this hackathon, **40 Bobcoins** will be automatically applied to your hackathon-provisioned IBM Bob account. These Bobcoins are intended to be sufficient for designing and building a compelling proof-of-concept submission." (quote via DDG search snippet of <https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf>; the PDF itself is binary and not text-extractable with the fetch tools).
- General Bobcoin economics (<https://bob.ibm.com/docs/ide/account/bobcoins>): Free trial 50 / Pro 50 / Pro+ 180 / Ultra 1000 Bobcoins per month; Enterprise packs 1,000 Bobcoins for $500 USD.
- The BeMyApp student program offers "Get 40 Bobcoins for 30 days" via trial link (<https://aibuilderschallenge-bob.bemyapp.com/>) — corroborates 40 as the typical promo allotment, still not a Sept-hackathon figure.

Planning assumption: budget for ~40 Bobcoins until "Access details" lands, and treat it as unconfirmed.

## 4. Rule changes / policy details

- **Pre-existing-code policy: STILL UNVERIFIED for September.** The only originality language on the Sept page is the prize fine print: "Submissions must be original and MIT-compliant." No September official-rules PDF exists — the S3 bucket (<https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/?list-type=2>) has 27 objects, newest dated 2026-08-29 (TechXchange guide); no Sept rules/guide upload. The May rules PDF ("Official Rules IBM Hackathon May 2026.pdf", 2026-04-09) exists but is binary-unreadable via these tools, so its exact pre-developed-technology wording could not be re-verified today.
- **Submission requirements (confirmed on the Sept page, "What to submit?" section):**
  - 📋 Basic Information: Project Title, Short Description, Long Description, Technology & Category Tags
  - 📸 Cover Image and Presentation: Cover Image, **Video Presentation**, **Slide Presentation**
  - 💻 App Hosting & Code Repository: Demo Application Platform, Application URL
  - "Important Requirements: • **Include any code or files where IBM Bob 2.0 assisted in the development.** • **Be sure to include the screenshots of IBM Bob task session summaries for your project.**"
  - i.e. the session-summary-screenshot and code-assisted-evidence requirements ARE in force for September.
- **Team size:** embedded event JSON has `"teamMembersLimit":6` (max 6 per team; not displayed as visible page text). Solo explicitly allowed ("Join a team or build solo").
- **Prizes (confirmed, unchanged):** "$10,000 total prize pool — 🥇 1st Place $5,000 / 🥈 2nd Place $3,000 / 🥉 3rd Place $2,000". Fine print: prizes may take up to 90 days; "Hackathon rules, prizes, and terms may change or be canceled at our discretion."
- **Judging criteria (published):** Application of Technology; Presentation; Business Value; Originality.
- **Challenge statement (published):** "Create a solution that improves a specific developer workflow, such as onboarding, debugging, code review, testing, application maintenance, or release and deployment processes… build a working prototype on a real or sample project… Leverage features like Agent mode, parallel tasks, subagents, and document understanding to manage and improve multiple steps, not just assist with coding."
- **Timeline:** milestones on /live: "Fri, Sep 25 15:00 UTC Kickoff · Registration closes" and "Sun, Sep 27 15:00 UTC Submissions close · Judging begins". Embedded JSON: `"startAt":"2026-09-25T15:00:00.000Z"`, `"endAt":"2026-09-27T15:00:00.000Z"` — but the internal `timelineEvents` entries read Start 19:00Z / **End 2026-09-27T21:00:00.000Z**, inconsistent with the public 15:00 UTC close. Public endAt + milestone text agree on 15:00 UTC; treat 21:00Z as a stale/internal artifact but re-check at sprint start. Also noteworthy: event JSON `"status":"DRAFT"` and `eventPrizes:[]` while the visible page is live — the page is being assembled in builder.io.
- Workshop unchanged: "Prompt, Build, Ship" hands-on workshop with BJ Hargrave (IBM Research), **Sept 24, 2026, 11:00 AM–12:30 PM ET** (<https://ibm-bobday.bemyapp.com/>, <https://developer.ibm.com/events/prompt-build-ship-virtual-hands-on-workshop-with-ibm-bob/>).

## 5. Dates / deadline

Confirmed unchanged, three sources:

- <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon>: "💻 Online Hackathon | ⏳ Build: 48 hours | 📅 September 25–27, 2026"
- /live: "You have until **Sep 27, 2026, 15:00 UTC** to submit." and "Registration closes the moment the event starts."
- <https://developer.ibm.com/events/ibm-bob-20-hackathon/>: "25 September 2026 at 11:00 GMT-4" (= 15:00 UTC), tagline "Your code meets your new AI dev partner." — links to the lablab event page.

## 6. How submission works

- Mechanism: "Submit your project through the lablab.ai platform before the deadline. Make sure all fields below are completed." → fields listed in §4. General guidance linked from the page as lablab.ai "Submission Guidelines".
- **Demo video length: NOT specified** on this event page (no minute cap given). Do not import the 3-minute cap from the BeMyApp student challenge — that is a different event.
- **Repo requirements:** the form asks for "Demo Application Platform" and "Application URL", plus "any code or files where IBM Bob 2.0 assisted"; no explicit "public GitHub repository with README" requirement is stated on this page (that wording belongs to the BeMyApp student challenge).
- Community/support: Discord <https://discord.gg/lablabai>, X <https://x.com/lablabai>.

## 7. New since the 15-sep morning snapshot

See Diff section below. Net-new discoveries of the afternoon (not necessarily page changes):
- The "Speakers, Mentors & Judges" section carries 2 NativelyAI names (morning note said judges not published).
- Confirmed the full submission checklist incl. Bob session-summary screenshots (verbatim, §4).
- Confirmed `teamMembersLimit: 6` from page JSON.
- Confirmed prize split $5K/$3K/$2K on-page.
- No new S3 uploads, no Sept rules PDF, no tracks, no IBM judges, no new blog/news posts (latest promo is still the Aug 5 announcement mirrored on Instagram/Facebook/LinkedIn: "Announcing the IBM Bob 2.0 Hackathon – the official second edition, hosted by IBM and lablab.ai").
- Context: AI Builders Conference (students) runs Sept 16; IBM Champions Bobathon NYC Sept 28 — adjacent events, not part of this hackathon.

---

## Diff vs 15-sep morning snapshot

Changed:
1. Registered builders: 10,680 → **10,700** (+20; "+227 in last 24h").
2. Teams forming: 1,739 → **1,742** (+3).
3. Judges: morning "NOT published" → a "Speakers, Mentors & Judges" section now lists **Pawel Czech (CEO, NativelyAI)** and **Andrea Marazzi (Founder & CCO, NativelyAI)**. No IBM judges yet; `externalRolePersons` still empty. (Cannot prove the section was empty at snapshot time — flagging as observed delta.)

Unchanged (verified):
- Tracks: still "TBA / Announced soon".
- 2nd-challenge teaser: still absent (only the "Second IBM Bob Hackathon" edition note).
- Bobcoins: still no Sept figure; "Access details TBA". (~40 remains a May-only number.)
- No September rules PDF in the S3 bucket (newest object 2026-08-29; bucket listing re-pulled today).
- Dates/deadline: Fri 25 → Sun 27 Sep, submissions close Sun 15:00 UTC.
- Prizes: $10,000 pool, $5K/$3K/$2K.
- Workshop "Prompt, Build, Ship" still on for 24-Sep (11:00 AM–12:30 PM ET, BJ Hargrave).
- Team limit 6 (from JSON; not visible text — morning snapshot had no figure).

Caveat: the embedded `timelineEvents` "End" is 2026-09-27T21:00:00Z while every public surface says 15:00 UTC — an internal inconsistency worth one re-check on sprint day, not a rule change.

## Re-verification 2026-09-16 (fetched 01:10–01:20 UTC; tavily_extract + raw-HTML JSON grep, same method as the 15-sep baseline)

Verdict per item vs the 15-sep afternoon snapshot above:

| Item | Verdict | Evidence |
|---|---|---|
| Tracks | **UNCHANGED** — still "TBA / Announced soon" | /live dashboard (lablab.ai/ai-hackathons/ibm-bob-2-hackathon/live) |
| Judges | **UNCHANGED** — still exactly 2 NativelyAI names (Pawel Czech, Andrea Marazzi); no IBM judges; embedded `externalRolePersons`/`eventRoles` still empty | event page raw HTML (builder.io payload) |
| 2nd challenge | **UNCHANGED** — still absent; zero hits for "BeMyApp"/"Bobathon"/second-challenge in raw HTML | event page raw |
| Sept Bobcoins | **UNCHANGED** — still "Access details TBA"; "bobcoin" appears nowhere on the event page (case-insensitive). Bobcoin economics page unchanged: Free 50 / Pro 50 / Pro+ 180 / Ultra 1000 monthly, $500 per 1000-coin pack, $0.50/coin overage | event page raw; <https://bob.ibm.com/docs/ide/account/bobcoins> |
| Rules / pre-existing-code policy | **UNCHANGED** — S3 bucket still has no Sept rules PDF (newest object 2026-08-29, nothing added for the 5th consecutive day; 27 objects total); only policy text remains "Submissions must be original and MIT-compliant" | <https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/?list-type=2> |
| Submission requirements | **UNCHANGED** — same basic-info + cover/video/slides fields; "screenshots of IBM Bob task session summaries" line still present; registration `status:"PUBLISHED"`, `participantsLimit:null` (no cap) | event page raw |
| Dates / deadline | **UNCHANGED** — `startAt` 2026-09-25T15:00:00Z, `endAt` 2026-09-27T15:00:00Z; /live: "You have until Sep 27, 2026, 15:00 UTC to submit"; milestones "Kickoff · Registration closes" Fri 15:00 UTC, "Submissions close · Judging begins" Sun 15:00 UTC. The `timelineEvents` 19:00Z/21:00Z shift persists — confirmed confined to that one field | /live + event page raw + developer.ibm.com |
| Prizes | **UNCHANGED** — $10,000 pool; $5,000 / $3,000 / $2,000 cards (each amount appears exactly once) | event page raw |
| Team size | **UNCHANGED** — `teamMembersLimit:6` | event page raw |
| Registered count | **CHANGED (backwards)** — /live now shows **10,420** registered / **1,698** teams forming (vs 10,700 / 1,742 on 15-sep) despite "+202 in last 24h". Net decrease with positive inflow ⇒ purge/dedup or baseline imprecision; does not affect the plan, re-check at sprint start | /live |

New observations (16-sep):

1. A BeMyApp **university-program** page offers "40 Bobcoins for 30 days" (<https://ibm.biz/university-bob>) — that offer belongs to the university program, **not** this event; do not book it as the Sept figure. (The related "AI Builders Conference with IBM Bob" ran Sep 16.)
2. The 24-Sep workshop time now **disagrees across sources**: developer.ibm.com lists 12:00 ET; the BeMyApp page (baseline source for 11:00–12:30 ET) is unchanged. The recording is the deliverable either way (SPRINT-RUNBOOK §2).
3. /live now surfaces "Tech partners 0" (absent from the baseline; unknown whether a delta).
4. Status flags: `active:true`, `signupActive:true`, `toBeAnnounced:false`. Two tavily_search sweeps found only promo reposts — no judges/tracks/Bobcoin announcements since 15-sep.

No prompt-injection content in any fetched page. Conclusion: every planning assumption in `docs/SPRINT-RUNBOOK.md` and `docs/BOBCOIN-BUDGET.md` built on the 15-sep snapshot remains valid 9 days before kickoff; the only moving number (registered count) does not affect the plan.

## Sprint-start checklist (re-check Fri 25-Sep before committing hours)

1. **Before 15:00 UTC Fri:** registration must be complete (it closes at kickoff) and team joined/formed (limit 6).
2. Re-pull <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon/live> — check whether **Tracks** left "TBA" and whether the deadline still reads Sun 27 15:00 UTC (also glance at the endAt/milestone consistency).
3. Re-check the main page **"Access details TBA"** block and the kickoff stream ("Hackathon Guide" item, 15:35 UTC Fri) for the **September Bobcoins figure**; until a number appears, assume ~40 and watch the usage gauge in the Bob IDE (gauge top-right / Settings → General / Bobalytics).
4. Re-list the S3 bucket (`?list-type=2`) for a September rules/guide PDF; if published, read the **pre-existing-code / pre-developed-technology** clause before reusing any prior work (current Sept-page language only says "Submissions must be original and MIT-compliant").
5. Check the **"Speakers, Mentors & Judges"** section for added IBM judges (relevant for demo framing).
6. In the lablab Discord, look for the mirrored announcement of tracks/judges/access; confirm whether a **public repo** is expected beyond "Demo Application Platform / Application URL" and whether a **video length cap** was set in the open submission form.
7. Prepare capture discipline from minute one: save **IBM Bob task session summary screenshots** and keep Bob-assisted files separable — both are explicit submission requirements.
8. Optional prep: watch the 24-Sep "Prompt, Build, Ship" workshop (BJ Hargrave) recording for Bob 2.0 setup/access mechanics before the kickoff.

## Sources

Fetched:
- https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon (simplified + full raw HTML; source of challenge/prizes/submission/judging/details/speakers text and embedded event JSON)
- https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon/live
- https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/?list-type=2
- https://developer.ibm.com/hackathons/ (renders "Loading page..." — JS-only, no data)
- https://developer.ibm.com/events/prompt-build-ship-virtual-hands-on-workshop-with-ibm-bob/
- https://developer.ibm.com/events/ibm-bob-20-hackathon/ (simplified + raw)
- https://ibm-bobday.bemyapp.com/

Fetched again 2026-09-16 (re-verification section above): the lablab event page (raw + extract), /live, the S3 listing, https://bob.ibm.com/docs/ide/account/bobcoins, developer.ibm.com event + workshop pages, and aibuilderschallenge-bob.bemyapp.com (via search-result extraction); tavily_search ×2.
- https://aibuilderschallenge-bob.bemyapp.com/
- https://bob.ibm.com/docs/ide/account/bobcoins
- https://entremotivator.com/hackathons/ibm-bob-2-hackathon/ (third-party mirror; first fetch failed, retry via DDG fetch_content succeeded)
- https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/Official%20Rules%20IBM%20Hackathon%20May%202026.pdf (binary — not text-extractable; recorded as unavailable for text)
- https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf (binary — quote taken from DDG search snippet instead)

Searched (DDG):
- "IBM Bob 2.0" hackathon lablab September 2026 judges tracks (first attempt bot-blocked, re-ran)
- IBM Bob 2.0 hackathon
- IBM Bob hackathon September 2026 rules bobcoins
- "IBM Bob 2.0 hackathon" announcement September 2026
- lablab.ai IBM Bob 2.0 hackathon judges announced
- IBM Bob 2.0 hackathon community.ibm.com OR dev.to OR news
