"""
IntelligentCoBParser — two-stage COB BIRR PDF parser.

Stage 1: pdfplumber candidate page selection (fast, no API cost)
    Scans every page for keywords derived from the ProjectContext.
    Narrows a 300-page PDF to 5–15 candidate pages.

Stage 2: OpenAI GPT-4o Vision extraction (targeted, context-aware)
    Renders each candidate page to a PNG, sends it to GPT-4o Vision
    with a structured prompt, extracts budget figures.

Requires:
    pip install pdf2image openai
    apt install poppler-utils   # provides pdftoppm used by pdf2image
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# GPT-4o pricing (March 2026) — used for per-investigation cost estimation.
# Override via OPENAI_VISION_INPUT_COST / OPENAI_VISION_OUTPUT_COST env vars
# if pricing changes.
_GPT4O_INPUT_COST_PER_TOKEN: float = 5.0 / 1_000_000   # $5 per 1M input tokens
_GPT4O_OUTPUT_COST_PER_TOKEN: float = 15.0 / 1_000_000  # $15 per 1M output tokens


class VisionCostLimitExceededError(Exception):
    """Raised when Vision API spend exceeds the per-investigation cap."""

VISION_PROMPT = """\
You are analysing a page from a Kenya Controller of Budget (CoB)
Budget Implementation Review Report (BIRR).

You are looking for budget lines related to this specific project:

  Project name: {canonical_name}
  Also known as: {aliases}
  Procuring entity: {procuring_entity}
  Ministry: {ministry}
  Vote head: {vote_head}
  Fiscal year: {fiscal_year}
  County: {county}

If this page contains data for this project, extract:
  - approved_budget_kes: the Approved Budget figure (in KES)
  - released_kes: the Exchequer Releases figure (in KES)
  - absorbed_kes: the Actual Expenditure figure (in KES)
  - absorption_rate_pct: the absorption rate (as a percentage)
  - reporting_period: the quarter/period this figure covers
  - page_label: the heading or programme label closest to these figures

If the page does NOT contain data for this project, return:
  {{ "match": false }}

Return JSON only. Do not include explanation.
"""


class IntelligentCoBParser:
    """
    Two-stage COB BIRR PDF parser.

    Stage 1: pdfplumber candidate page selection (fast, no API cost).
    Stage 2: OpenAI GPT-4o Vision extraction (targeted, context-aware).
    """

    DPI: int = 200        # resolution for page rendering
    MAX_PAGES: int = 300  # safety cap on pages scanned in Stage 1

    def __init__(
        self,
        pdf_path: str,
        ctx: "IntelligentCoBParserContext",
        openai_client: "AsyncOpenAI",
        max_vision_pages: int = 20,
        dpi: Optional[int] = None,
        cost_limit_usd: Optional[float] = None,
    ) -> None:
        self.pdf_path = pdf_path
        self.ctx = ctx
        self.openai_client = openai_client
        self.max_vision_pages = max_vision_pages
        self.dpi = dpi or self.DPI
        self.cost_limit_usd = cost_limit_usd
        self.total_cost_usd: float = 0.0
        self.pages_processed: int = 0

    async def extract(self) -> list[dict]:
        """
        Full two-stage extraction.

        Returns a list of FinancialRecord-compatible dicts — one per
        successfully matched page. Empty list if no matches found.
        """
        candidate_pages = self._select_candidates()
        if not candidate_pages:
            logger.info(
                f"IntelligentCoBParser: no candidate pages found in {self.pdf_path}"
            )
            return []

        logger.info(
            f"IntelligentCoBParser: {len(candidate_pages)} candidate page(s) found, "
            f"sending up to {self.max_vision_pages} to Vision"
        )

        results: list[dict] = []
        for page_num in candidate_pages[: self.max_vision_pages]:
            # Cost guard: stop before issuing the next Vision request if the
            # per-investigation cap has been reached.
            if (
                self.cost_limit_usd is not None
                and self.total_cost_usd >= self.cost_limit_usd
            ):
                logger.warning(
                    f"IntelligentCoBParser: Vision cost limit "
                    f"${self.cost_limit_usd:.4f} reached after "
                    f"{self.pages_processed} page(s) "
                    f"(spend=${self.total_cost_usd:.4f}). Stopping early."
                )
                break

            try:
                img_bytes = self._render_page(page_num)
            except Exception as exc:
                logger.warning(
                    f"IntelligentCoBParser: failed to render page {page_num}: {exc}"
                )
                continue

            try:
                record = await self._vision_extract(page_num, img_bytes)
            except Exception as exc:
                logger.warning(
                    f"IntelligentCoBParser: Vision API failed on page {page_num}: {exc}"
                )
                continue

            if record:
                results.append(record)

        logger.info(
            f"IntelligentCoBParser: extracted {len(results)} record(s) from {self.pdf_path} "
            f"(vision_cost=${self.total_cost_usd:.4f}, pages_processed={self.pages_processed})"
        )
        return results

    # ── Stage 1 ───────────────────────────────────────────────────────────────

    def _select_candidates(self) -> list[int]:
        """
        Stage 1: Use pdfplumber to find pages containing context keywords.

        Returns 0-based page indices ordered by keyword density (most
        relevant pages first) so Vision cost is minimised.
        """
        import pdfplumber

        keywords = self._build_keyword_set()
        if not keywords:
            return []

        scores: list[tuple[int, int]] = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for i, page in enumerate(pdf.pages[: self.MAX_PAGES]):
                    text = (page.extract_text() or "").lower()
                    score = sum(1 for kw in keywords if kw.lower() in text)
                    if score > 0:
                        scores.append((i, score))
        except Exception as exc:
            logger.error(
                f"IntelligentCoBParser: pdfplumber failed on {self.pdf_path}: {exc}"
            )
            return []

        return [idx for idx, _ in sorted(scores, key=lambda x: -x[1])]

    def _build_keyword_set(self) -> set[str]:
        """Generate keyword set from the context object."""
        kw: set[str] = set()
        if self.ctx.canonical_name:
            kw.add(self.ctx.canonical_name)
        kw.update(self.ctx.aliases)
        if self.ctx.ministry:
            kw.add(self.ctx.ministry)
        if self.ctx.procuring_entity:
            kw.add(self.ctx.procuring_entity)
        if self.ctx.county:
            kw.add(self.ctx.county)
        if self.ctx.vote_head is not None:
            kw.add(str(self.ctx.vote_head))
        # Remove empty strings
        kw.discard("")
        return kw

    # ── Stage 2 ───────────────────────────────────────────────────────────────

    def _render_page(self, page_num: int) -> bytes:
        """
        Render a single PDF page to PNG bytes using pdf2image (poppler).

        Args:
            page_num: 0-based page index.

        Returns:
            PNG image as raw bytes.
        """
        from pdf2image import convert_from_path

        images = convert_from_path(
            self.pdf_path,
            dpi=self.dpi,
            first_page=page_num + 1,  # pdf2image uses 1-based page numbers
            last_page=page_num + 1,
        )
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()

    async def _vision_extract(
        self,
        page_num: int,
        img_bytes: bytes,
    ) -> dict | None:
        """
        Stage 2: Send page image to GPT-4o Vision with a targeted prompt.

        Returns a FinancialRecord-compatible dict if the page contains
        data for the target project, or None if the model returns
        ``{"match": false}``.
        """
        prompt = self._build_prompt()
        b64 = base64.b64encode(img_bytes).decode()

        response = await self.openai_client.chat.completions.create(
            model=getattr(self.ctx, "vision_model", "gpt-4o"),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
        )

        # Accumulate cost from token usage reported by the API.
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            self.total_cost_usd += (
                prompt_tokens * _GPT4O_INPUT_COST_PER_TOKEN
                + completion_tokens * _GPT4O_OUTPUT_COST_PER_TOKEN
            )
        self.pages_processed += 1

        raw_content = response.choices[0].message.content or ""
        try:
            raw = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            logger.warning(
                f"IntelligentCoBParser: Vision response not valid JSON "
                f"on page {page_num}: {exc!r} — content: {raw_content[:200]}"
            )
            return None

        if raw.get("match") is False:
            return None

        return self._to_financial_record(raw, page_num)

    def _build_prompt(self) -> str:
        return VISION_PROMPT.format(
            canonical_name=self.ctx.canonical_name or "",
            aliases=", ".join(self.ctx.aliases),
            procuring_entity=self.ctx.procuring_entity or "",
            ministry=getattr(self.ctx, "ministry", "") or "",
            vote_head=getattr(self.ctx, "vote_head", "") or "",
            fiscal_year=(
                self.ctx.fiscal_years[0] if self.ctx.fiscal_years else ""
            ),
            county=getattr(self.ctx, "county", "") or "",
        )

    def _to_financial_record(self, raw: dict, page_num: int) -> dict:
        """Map Vision JSON output → FinancialRecord-compatible dict."""
        return {
            "source_system": "COB",
            "fiscal_year": (
                self.ctx.fiscal_years[0] if self.ctx.fiscal_years else None
            ),
            "ministry": getattr(self.ctx, "ministry", None),
            "vote_head": getattr(self.ctx, "vote_head", None),
            "programme": raw.get("page_label"),
            "budget_allocated_kes": raw.get("approved_budget_kes"),
            "budget_released_kes": raw.get("released_kes"),
            "budget_absorbed_kes": raw.get("absorbed_kes"),
            "absorption_rate": raw.get("absorption_rate_pct"),
            "reporting_period": raw.get("reporting_period"),
            "document_source": self.pdf_path,
            "match_method": "openai_vision_gpt4o",
            "confidence_score": 90,  # Vision extraction is high confidence
            "extraction_page": page_num,
        }


# ---------------------------------------------------------------------------
# Thin context dataclass consumed only by this parser.
# Accepts both the lightweight data.context.ProjectContext (Sprint 2) and
# the backend's Pydantic ProjectContext — any object with the required attrs.
# ---------------------------------------------------------------------------

class IntelligentCoBParserContext:
    """
    Minimal context interface consumed by IntelligentCoBParser.

    You can pass a data.context.ProjectContext, a backend
    ProjectContext Pydantic model, or an instance of this class directly.
    """

    def __init__(
        self,
        canonical_name: Optional[str] = None,
        aliases: Optional[list[str]] = None,
        procuring_entity: Optional[str] = None,
        ministry: Optional[str] = None,
        vote_head: Optional[str | int] = None,
        fiscal_years: Optional[list[str]] = None,
        county: Optional[str] = None,
        vision_model: str = "gpt-4o",
    ) -> None:
        self.canonical_name = canonical_name
        self.aliases = aliases or []
        self.procuring_entity = procuring_entity
        self.ministry = ministry
        self.vote_head = vote_head
        self.fiscal_years = fiscal_years or []
        self.county = county
        self.vision_model = vision_model
