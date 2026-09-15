"""Piece 2 — claim -> evidence linkage validation.

A claim is *valid* iff it carries at least one ref AND every ref it carries
is in ``evidence.ref_ids()``. The linkage rate feeds the ``claim_linkage_rate``
metric of the eval harness (piece 4).
"""

from __future__ import annotations

from pmg.contracts import Evidence, InvalidClaimRef, LinkageReport, Postmortem


def validate_linkage(pm: Postmortem, evidence: Evidence) -> LinkageReport:
    """Validate every claim in *pm* against *evidence*.

    Returns a :class:`~pmg.contracts.LinkageReport`; invalid claims are
    reported with their section id, text and the refs that are not valid
    evidence ids (claims with no refs at all are invalid with ``bad_refs``
    empty — the missing linkage is the finding).
    """
    valid_ids = evidence.ref_ids()
    total = 0
    valid = 0
    invalid: list[InvalidClaimRef] = []
    for section in pm.sections:
        for claim in section.claims:
            total += 1
            bad_refs = [r for r in claim.refs if r not in valid_ids]
            if claim.refs and not bad_refs:
                valid += 1
            else:
                invalid.append(
                    InvalidClaimRef(
                        section_id=section.id,
                        claim_text=claim.text,
                        bad_refs=bad_refs,
                    )
                )
    rate = (valid / total) if total else 0.0
    return LinkageReport(
        total_claims=total, valid_claims=valid, rate=rate, invalid=invalid
    )
