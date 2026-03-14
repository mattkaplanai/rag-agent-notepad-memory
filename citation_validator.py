"""
Citation validator: check that decision citations are well-formed and grounded.

- Format/link check: each applicable_regulation should match a known source (CITATION_MAP)
  so the passenger gets a clickable link; unknown entries are flagged.
- Cross-check: citations in the Writer's decision should appear in the Researcher's
  "APPLICABLE RULES FOR CITATION" section so we only cite what was actually found.
- Retrieval grounding: each citation should appear in the chunks that the Researcher's
  search_regulations tool actually returned — so we know the Researcher "found" it.

Use this after the Writer produces the decision to keep citations trustworthy as
the project grows (more regulations, more agents).
"""

from dataclasses import dataclass, field
from typing import List, Optional

from citation_links import get_citation_link


# Section header the Researcher is prompted to output (must match multi_agent.RESEARCHER_PROMPT)
APPLICABLE_RULES_HEADER = "APPLICABLE RULES FOR CITATION"


@dataclass
class CitationValidationResult:
    """Result of validating applicable_regulations against known sources and Researcher output."""

    # Citations that have a known link (CITATION_MAP)
    with_link: List[str] = field(default_factory=list)
    # Citations that do not match any known pattern — no link will be shown
    without_link: List[str] = field(default_factory=list)
    # Citations that the Writer used but were not listed in Researcher's APPLICABLE RULES section
    not_in_researcher: List[str] = field(default_factory=list)
    # Citations that appear in the retrieval chunks (Researcher actually found them)
    grounded_in_retrieval: List[str] = field(default_factory=list)
    # Citations that do NOT appear in retrieval (no evidence in what Researcher retrieved)
    not_grounded_in_retrieval: List[str] = field(default_factory=list)
    # Whether validation passed without warnings (link + researcher list + grounding when chunks provided)
    is_ok: bool = True
    # Human-readable summary for logs/UI
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.summary:
            self.summary = _build_summary(self)


def _build_summary(result: "CitationValidationResult") -> str:
    parts = []
    if result.with_link:
        parts.append(f"{len(result.with_link)} citation(s) with official link")
    if result.without_link:
        parts.append(f"{len(result.without_link)} without link (unknown regulation name)")
    if result.not_in_researcher:
        parts.append(f"{len(result.not_in_researcher)} not listed in Researcher output")
    if result.grounded_in_retrieval:
        parts.append(f"{len(result.grounded_in_retrieval)} grounded in retrieval")
    if result.not_grounded_in_retrieval:
        parts.append(f"{len(result.not_grounded_in_retrieval)} not found in retrieval")
    if not parts:
        return "No citations to validate"
    return "; ".join(parts)


def _extract_researcher_cited_rules(researcher_output: Optional[str]) -> List[str]:
    """
    Parse the Researcher's "APPLICABLE RULES FOR CITATION" section and return
    normalized rule names (one per line, stripped). Returns [] if section not found.
    """
    if not researcher_output or not isinstance(researcher_output, str):
        return []
    text = researcher_output.strip()
    header = APPLICABLE_RULES_HEADER.upper()
    # Find section: look for the header (case-insensitive)
    idx = text.upper().find(header)
    if idx == -1:
        return []
    # Start after the header line
    rest = text[idx + len(header) :].lstrip()
    lines = rest.splitlines()
    rules = []
    for line in lines:
        line = line.strip()
        if not line:
            break
        # Skip lines that look like section separators or markdown
        if line.startswith("#") or line.startswith("---") or line.upper() == line and len(line) > 3:
            break
        rules.append(line)
    return rules


def _normalize_rule_for_match(reg: str) -> str:
    """Normalize a regulation string for fuzzy matching (e.g. Writer vs Researcher)."""
    if not reg:
        return ""
    # Take the part before " — " or " - " as the canonical name; else use first segment
    for sep in (" — ", " - ", " – "):
        if sep in reg:
            reg = reg.split(sep)[0].strip()
            break
    return reg.strip().lower()


def _rule_in_researcher_list(reg: str, researcher_rules: List[str]) -> bool:
    """True if reg (or its normalized form) appears in researcher_rules (or as substring)."""
    if not researcher_rules:
        return True  # No list to check against — don't flag
    norm = _normalize_rule_for_match(reg)
    if not norm:
        return True
    for r in researcher_rules:
        if norm in _normalize_rule_for_match(r) or _normalize_rule_for_match(r) in norm:
            return True
    return False


def _citation_in_retrieval(reg: str, retrieval_chunks: List[str]) -> bool:
    """True if the regulation name (e.g. 14 CFR 259.4) appears in any retrieval chunk (case-insensitive)."""
    if not retrieval_chunks or not reg:
        return False
    norm = _normalize_rule_for_match(reg)
    if not norm or len(norm) < 4:
        return False
    combined = " ".join(retrieval_chunks).lower()
    return norm in combined


def validate_citations(
    applicable_regulations: List[str],
    researcher_output: Optional[str] = None,
    retrieval_chunks: Optional[List[str]] = None,
) -> CitationValidationResult:
    """
    Validate decision citations.

    - For each item in applicable_regulations: if get_citation_link(reg) returns
      a link, it goes to with_link; else to without_link.
    - If researcher_output is provided, parse "APPLICABLE RULES FOR CITATION" and
      put any Writer citation that doesn't appear there into not_in_researcher.
    - If retrieval_chunks is provided (chunks returned by search_regulations), check
      that each citation appears in at least one chunk (grounded_in_retrieval vs
      not_grounded_in_retrieval).

    Returns CitationValidationResult with is_ok = False if there are without_link,
    not_in_researcher, or (when retrieval_chunks given) not_grounded_in_retrieval.
    """
    with_link: List[str] = []
    without_link: List[str] = []
    researcher_rules = _extract_researcher_cited_rules(researcher_output)
    retrieval = retrieval_chunks or []

    for reg in applicable_regulations or []:
        if not reg or not isinstance(reg, str):
            continue
        s = reg.strip()
        if not s:
            continue
        url, _ = get_citation_link(s)
        if url:
            with_link.append(s)
        else:
            without_link.append(s)

    not_in_researcher = [
        r for r in (applicable_regulations or [])
        if r and isinstance(r, str) and r.strip()
        and not _rule_in_researcher_list(r.strip(), researcher_rules)
    ]

    grounded_in_retrieval: List[str] = []
    not_grounded_in_retrieval: List[str] = []
    if retrieval:
        for r in (applicable_regulations or []):
            if not r or not isinstance(r, str) or not r.strip():
                continue
            s = r.strip()
            if _citation_in_retrieval(s, retrieval):
                grounded_in_retrieval.append(s)
            else:
                not_grounded_in_retrieval.append(s)

    is_ok = not (
        bool(without_link)
        or bool(not_in_researcher)
        or (bool(retrieval) and bool(not_grounded_in_retrieval))
    )
    result = CitationValidationResult(
        with_link=with_link,
        without_link=without_link,
        not_in_researcher=not_in_researcher,
        grounded_in_retrieval=grounded_in_retrieval,
        not_grounded_in_retrieval=not_grounded_in_retrieval,
        is_ok=is_ok,
        summary="",
    )
    result.summary = _build_summary(result)
    return result


def format_validation_for_log(result: CitationValidationResult) -> str:
    """Format validation result as a few log lines for agent_log or terminal."""
    lines = ["🔗 **Citation check:** " + result.summary]
    if result.without_link:
        lines.append("   ⚠️ No official link (add to citation_links.CITATION_MAP if valid):")
        for r in result.without_link[:5]:
            lines.append(f"      - {r[:80]}{'…' if len(r) > 80 else ''}")
        if len(result.without_link) > 5:
            lines.append(f"      … and {len(result.without_link) - 5} more")
    if result.not_in_researcher:
        lines.append("   ⚠️ Cited but not in Researcher's APPLICABLE RULES list:")
        for r in result.not_in_researcher[:5]:
            lines.append(f"      - {r[:80]}{'…' if len(r) > 80 else ''}")
        if len(result.not_in_researcher) > 5:
            lines.append(f"      … and {len(result.not_in_researcher) - 5} more")
    if result.not_grounded_in_retrieval:
        lines.append("   ⚠️ Not found in retrieval (Researcher's search did not return this text):")
        for r in result.not_grounded_in_retrieval[:5]:
            lines.append(f"      - {r[:80]}{'…' if len(r) > 80 else ''}")
        if len(result.not_grounded_in_retrieval) > 5:
            lines.append(f"      … and {len(result.not_grounded_in_retrieval) - 5} more")
    if result.is_ok and result.with_link:
        lines.append("   ✓ All citations have official links, match Researcher output, and are grounded in retrieval.")
    return "\n".join(lines)
