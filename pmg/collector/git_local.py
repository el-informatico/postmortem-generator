"""Local git access via subprocess (piece 1, collector).

All repository reads go through :class:`GitRepo` — a thin, checked wrapper
around the ``git`` CLI. Stdlib only, deterministic, no network.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pmg.collector.errors import CollectorError
from pmg.contracts import CommitInfo

#: Marker appended to a diff cut at ``max_diff_bytes`` (also used by the
#: diff parser in szz.py to detect truncation).
DIFF_TRUNCATED_MARKER = "\n... [diff truncated]"

_GIT_TIMEOUT = 60  # seconds per git invocation

# pre-release tag suffixes — an -rc/-alpha/-beta/-M tag is not a release
_PRE_RELEASE_RE = re.compile(
    r"[-_.](?:rc|cr|alpha|beta|ea|m)\d*$", re.IGNORECASE
)

# Porcelain blame header: "<sha> <orig_lineno> <final_lineno> [<num_lines>]"
_BLAME_HEADER_RE = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)(?: (\d+))?$")


class GitError(CollectorError):
    """A git command failed."""


class GitRepo:
    """Read-only helper over a local git repository (worktree or bare)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # -- plumbing -----------------------------------------------------------
    def _run(self, *args: str) -> str:
        """Run ``git -C <path> <args>``; return stdout; raise GitError on fail."""
        proc = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        if proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed in {self.path}: {proc.stderr.strip()[:500]}"
            )
        return proc.stdout

    # -- public API ---------------------------------------------------------
    def resolve_sha(self, short_or_full: str) -> str:
        """Resolve any committish (short sha, full sha, ``sha~1``, ...) to a
        full 40-char commit sha."""
        out = self._run("rev-parse", "--verify", f"{short_or_full}^{{commit}}")
        return out.strip()

    def commit_info(self, sha: str, max_diff_bytes: int = 200_000) -> CommitInfo:
        """Collect the CommitInfo contract fields for ``sha``.

        ``url`` is left empty — the caller knows the GitHub repo and fills it.
        The diff is truncated to ``max_diff_bytes`` with a trailing
        ``DIFF_TRUNCATED_MARKER`` when it is longer.
        """
        full = self.resolve_sha(sha)
        # %x1f (unit separator) between fields; maxsplit keeps the message
        # intact even if it ever contained the separator.
        meta = self._run(
            "show", "-s", f"--format=%H%x1f%an%x1f%aI%x1f%cI%x1f%s%x1f%B", full
        ).rstrip("\n")
        fields = meta.split("\x1f", 5)
        if len(fields) != 6:
            raise GitError(f"unexpected git show output for {full}: {meta[:200]}")
        full_sha, author, author_date, committer_date, subject, message = fields

        files = [
            line
            for line in self._run(
                "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", full
            ).splitlines()
            if line.strip()
        ]

        diff = self._run("show", "--format=", "--unified=3", full)
        if len(diff) > max_diff_bytes:
            diff = diff[:max_diff_bytes] + DIFF_TRUNCATED_MARKER

        return CommitInfo(
            sha=full_sha,
            short_sha=full_sha[:10],
            subject=subject,
            author=author,
            author_date=author_date,
            message=message,
            files=files,
            diff=diff,
            url="",
            committer_date=committer_date,
        )

    def tags_containing(self, sha: str) -> list[str]:
        """All tags containing ``sha``, version-sorted ascending.

        ``--sort=version:refname`` so e.g. ``curl-8_10_0`` does not shadow
        ``curl-8_4_0`` the way plain alphabetical order would.
        """
        full = self.resolve_sha(sha)
        return [
            t.strip()
            for t in self._run(
                "tag", "--contains", full, "--sort=version:refname"
            ).splitlines()
            if t.strip()
        ]

    def tag_date(self, tag: str) -> str:
        """ISO-8601 creator date of *tag* (tagger date for annotated tags,
        commit date for lightweight ones)."""
        raw = self._run(
            "for-each-ref",
            f"refs/tags/{tag}",
            "--format=%(creatordate:iso-strict)",
        ).strip()
        return raw

    def first_tag_containing(self, sha: str) -> tuple[str, str] | None:
        """``(tag, ISO-8601 date)`` of the earliest-version NON-pre-release
        tag containing ``sha`` (falls back to the earliest tag at all when
        every containing tag is a pre-release), or ``None``.
        """
        tags = self.tags_containing(sha)
        if not tags:
            return None
        stable = [t for t in tags if not _PRE_RELEASE_RE.search(t)]
        chosen = (stable or tags)[0]
        return chosen, self.tag_date(chosen)

    def blame_lines(
        self, sha: str, file: str, start: int, end: int
    ) -> list[tuple[int, str]]:
        """Blame ``file`` lines ``start..end`` (inclusive, 1-based, in the
        version at ``sha``) and return ``[(line_number, commit_sha), ...]``
        in file order."""
        out = self._run(
            "blame", "--porcelain", f"-L{start},{end}", sha, "--", file
        )
        results: list[tuple[int, str]] = []
        current_sha = ""
        current_line = 0
        for line in out.splitlines():
            header = _BLAME_HEADER_RE.match(line)
            if header:
                current_sha = header.group(1)
                current_line = int(header.group(3))
            elif line.startswith("\t"):
                # content line for the most recent header
                results.append((current_line, current_sha))
        return results

    def log_pickaxe(
        self,
        s: str,
        file: str | None = None,
        before: str | None = None,
    ) -> list[tuple[str, str]]:
        """Commits where the occurrence count of string ``s`` changed
        (``git log -S``), as ``[(sha, author_date), ...]`` OLDEST FIRST —
        the first hit is the commit that introduced the string.

        ``file`` restricts the search to one path; ``before`` (ISO date)
        excludes commits dated after it.
        """
        args = ["log", f"--format=%H%x09%aI", f"-S{s}", "--reverse"]
        if before:
            args.append(f"--before={before}")
        if file:
            args += ["--", file]
        out = self._run(*args)
        pairs: list[tuple[str, str]] = []
        for line in out.splitlines():
            if "\t" in line:
                sha, date = line.split("\t", 1)
                pairs.append((sha, date))
        return pairs
