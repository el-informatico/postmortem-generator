"""Piece 1: deterministic evidence collector (no AI anywhere).

Public surface (see docs/CONTRACTS.md):
    collect_case()      — CaseConfig -> Evidence
    GitHubClient        — cached GitHub REST client
    GitRepo             — checked local git access
    CollectorError / OfflineCacheMiss — error contract
"""
from pmg.collector.collect import collect_case
from pmg.collector.errors import CollectorError, OfflineCacheMiss
from pmg.collector.github_api import GitHubAPIError, GitHubClient
from pmg.collector.git_local import GitError, GitRepo

__all__ = [
    "collect_case",
    "GitHubClient",
    "GitRepo",
    "CollectorError",
    "OfflineCacheMiss",
    "GitHubAPIError",
    "GitError",
]
