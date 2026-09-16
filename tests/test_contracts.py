"""Tests for the shared contract helpers (piece 0).

UTC normalization (``utc_iso``/``utc_date``) keeps git's offset-carrying
timestamps and the GitHub API's UTC timestamps on one day grid — the
property the B7 timeline curation (push/close merging) depends on.
"""

from __future__ import annotations

from pmg.contracts import (
    CaseConfig,
    CommitInfo,
    Evidence,
    IntroducerCandidate,
    IssueThread,
    ReleaseInfo,
    utc_date,
    utc_iso,
)


class TestUtcIso:
    def test_offsets_normalize_to_utc(self) -> None:
        # 00:08+01:00 is 23:08Z on the PREVIOUS day
        assert utc_iso("2020-02-17T00:08:48+01:00") == "2020-02-16T23:08:48Z"
        assert utc_iso("2023-10-11T07:34:19+02:00") == "2023-10-11T05:34:19Z"
        assert utc_iso("2020-02-16T23:09:09Z") == "2020-02-16T23:09:09Z"

    def test_naive_treated_as_utc(self) -> None:
        assert utc_iso("2020-02-16T23:09:09") == "2020-02-16T23:09:09Z"

    def test_empty_and_junk(self) -> None:
        assert utc_iso("") == ""
        assert utc_date("") == ""
        # unparseable input passes through unchanged, never raises
        assert utc_iso("not a date") == "not a date"

    def test_utc_date_uses_utc_day(self) -> None:
        assert utc_date("2020-02-17T00:08:48+01:00") == "2020-02-16"


class TestEvidenceRoundTrip:
    def test_new_fields_round_trip(self, tmp_path) -> None:
        ev = Evidence(
            case=CaseConfig(name="c", repo="o/r", issues=[1], fix_sha="abc"),
            fix_commit=CommitInfo(
                sha="a" * 40, short_sha="a" * 10, subject="s", author="au",
                author_date="2023-10-11T05:34:19Z", message="m",
                files=["f"], diff="d", url="u",
                committer_date="2023-10-11T05:34:19Z",
            ),
            issues=[
                IssueThread(
                    number=1, title="t", state="closed", author="a",
                    created_at="2020-02-11T06:38:35Z", body="b",
                    closed_at="2020-02-16T23:09:09Z",
                    merged_at="", is_pull_request=True,
                )
            ],
            introducer_candidates=[
                IntroducerCandidate(
                    sha="b" * 40, short_sha="b" * 10, subject="s", author="a",
                    author_date="2020-02-14T15:16:54Z", methods=["szz-blame"],
                    score=0.7, committer_date="2020-02-16T23:08:48Z",
                )
            ],
            releases=[
                ReleaseInfo(
                    tag="curl-8_4_0", version="8.4.0", date="2023-10-11",
                    contains_sha="a" * 40, role="fix",
                    url="https://github.com/o/r/releases/tag/curl-8_4_0",
                )
            ],
            timeline=[],
        )
        path = tmp_path / "evidence.json"
        ev.save(path)
        assert Evidence.load(path).to_dict() == ev.to_dict()
        # release ref ids participate in the linkage universe
        assert "release:curl-8_4_0" in ev.ref_ids()

    def test_old_evidence_without_new_fields_loads(self) -> None:
        old = {
            "case": {"name": "c", "repo": "o/r", "issues": [1]},
            "fix_commit": {
                "sha": "a" * 40, "short_sha": "a" * 10, "subject": "s",
                "author": "au", "author_date": "2023-10-11T05:34:19Z",
                "message": "m", "files": ["f"], "diff": "d",
            },
            "issues": [
                {
                    "number": 1, "title": "t", "state": "open", "author": "a",
                    "created_at": "2020-02-11T06:38:35Z", "body": "b",
                }
            ],
            "introducer_candidates": [],
            "timeline": [],
            "meta": {},
        }
        ev = Evidence.from_dict(old)
        assert ev.fix_commit.committer_date == ""
        assert ev.issues[0].closed_at == ""
        assert ev.releases == []
