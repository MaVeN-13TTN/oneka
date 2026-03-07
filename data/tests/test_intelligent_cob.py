"""
Sprint 3 — IntelligentCoBParser tests.

All OpenAI API calls and pdf2image rendering are mocked.
No real PDF, poppler, or network calls are made.

Run with:
    source data/venv-data/bin/activate
    python -m pytest data/tests/test_intelligent_cob.py -v
"""

from __future__ import annotations

import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _make_ctx(
    canonical_name="Rural Health Centre Marsabit",
    aliases=None,
    procuring_entity="Ministry of Health",
    ministry="Ministry of Health",
    vote_head="1073",
    fiscal_years=None,
    county="Marsabit",
):
    from data.context import ProjectContext

    return ProjectContext(
        canonical_name=canonical_name,
        aliases=aliases or ["Marsabit Health Centre"],
        procuring_entity=procuring_entity,
        ministry=ministry,
        vote_head=vote_head,
        fiscal_years=fiscal_years or ["2023/2024"],
        county=county,
    )


def _make_client(response_json: dict | None = None):
    """Return a fake AsyncOpenAI client with a mocked completions endpoint."""
    content = json.dumps(response_json) if response_json is not None else "{}"
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    completion = SimpleNamespace(choices=[choice])

    async def fake_create(**kwargs):
        return completion

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=fake_create)
    return client


# =============================================================================
# data.context.ProjectContext — new fields
# =============================================================================


class TestProjectContextNewFields:
    def test_defaults_for_new_fields(self):
        from data.context import ProjectContext

        ctx = ProjectContext()
        assert ctx.ministry is None
        assert ctx.county is None
        assert ctx.vote_head is None

    def test_new_fields_populated(self):
        from data.context import ProjectContext

        ctx = ProjectContext(
            canonical_name="Iten County Referral Hospital",
            ministry="Ministry of Health",
            county="Elgeyo-Marakwet",
            vote_head="1062",
        )
        assert ctx.ministry == "Ministry of Health"
        assert ctx.county == "Elgeyo-Marakwet"
        assert ctx.vote_head == "1062"

    def test_existing_fields_unaffected(self):
        """Adding new fields must not break existing callers."""
        from data.context import ProjectContext

        ctx = ProjectContext(
            canonical_name="Old caller",
            aliases=["alias1"],
            fiscal_years=["2022/2023"],
        )
        assert ctx.canonical_name == "Old caller"
        assert ctx.aliases == ["alias1"]
        assert ctx.fiscal_years == ["2022/2023"]
        # new fields default to None
        assert ctx.ministry is None


# =============================================================================
# IntelligentCoBParserContext
# =============================================================================


class TestIntelligentCoBParserContext:
    def test_defaults(self):
        from data.parsers.intelligent_cob import IntelligentCoBParserContext

        ctx = IntelligentCoBParserContext()
        assert ctx.canonical_name is None
        assert ctx.aliases == []
        assert ctx.fiscal_years == []
        assert ctx.vision_model == "gpt-4o"

    def test_fully_populated(self):
        from data.parsers.intelligent_cob import IntelligentCoBParserContext

        ctx = IntelligentCoBParserContext(
            canonical_name="Mombasa Road Bypass",
            aliases=["Bypass Phase 1"],
            ministry="Ministry of Transport",
            vote_head="1091",
            county="Mombasa",
            fiscal_years=["2023/2024"],
            procuring_entity="KeNHA",
        )
        assert ctx.canonical_name == "Mombasa Road Bypass"
        assert ctx.vote_head == "1091"


# =============================================================================
# _build_keyword_set
# =============================================================================


class TestBuildKeywordSet:
    def _parser(self, ctx=None, client=None):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        return IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=ctx or _make_ctx(),
            openai_client=client or _make_client(),
        )

    def test_includes_canonical_name(self):
        p = self._parser()
        kws = p._build_keyword_set()
        assert "Rural Health Centre Marsabit" in kws

    def test_includes_aliases(self):
        p = self._parser()
        kws = p._build_keyword_set()
        assert "Marsabit Health Centre" in kws

    def test_includes_ministry(self):
        p = self._parser()
        kws = p._build_keyword_set()
        assert "Ministry of Health" in kws

    def test_includes_county(self):
        p = self._parser()
        kws = p._build_keyword_set()
        assert "Marsabit" in kws

    def test_includes_vote_head(self):
        p = self._parser()
        kws = p._build_keyword_set()
        assert "1073" in kws

    def test_includes_procuring_entity(self):
        p = self._parser()
        kws = p._build_keyword_set()
        assert "Ministry of Health" in kws

    def test_no_empty_strings(self):
        from data.context import ProjectContext

        ctx = ProjectContext(canonical_name="", aliases=[], ministry=None)
        p = self._parser(ctx=ctx)
        kws = p._build_keyword_set()
        assert "" not in kws


# =============================================================================
# _select_candidates
# =============================================================================


class TestSelectCandidates:
    def _parser(self, ctx=None):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        return IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=ctx or _make_ctx(),
            openai_client=_make_client(),
        )

    def _fake_pdf(self, pages_text: list[str]):
        """Return a pdfplumber context manager mock with custom page text."""
        pages = []
        for text in pages_text:
            page = MagicMock()
            page.extract_text.return_value = text
            pages.append(page)

        pdf_mock = MagicMock()
        pdf_mock.__enter__ = MagicMock(return_value=pdf_mock)
        pdf_mock.__exit__ = MagicMock(return_value=False)
        pdf_mock.pages = pages
        return pdf_mock

    def test_no_matches_returns_empty(self):
        p = self._parser()
        pages = ["totally unrelated text"] * 5
        with patch("pdfplumber.open", return_value=self._fake_pdf(pages)):
            result = p._select_candidates()
        assert result == []

    def test_single_match(self):
        p = self._parser()
        pages = [
            "Ministry of Health rural health centre marsabit vote 1073",
            "unrelated content about bridges",
        ]
        with patch("pdfplumber.open", return_value=self._fake_pdf(pages)):
            result = p._select_candidates()
        assert 0 in result
        assert 1 not in result

    def test_higher_density_ranked_first(self):
        p = self._parser()
        pages = [
            # page 0: two keyword hits
            "Rural Health Centre Marsabit 1073",
            # page 1: one keyword hit
            "Ministry of Health unrelated",
        ]
        with patch("pdfplumber.open", return_value=self._fake_pdf(pages)):
            result = p._select_candidates()
        assert result[0] == 0  # highest density first

    def test_empty_keyword_set_returns_empty(self):
        from data.context import ProjectContext

        ctx = ProjectContext()  # no fields set — keyword set will be empty
        p = self._parser(ctx=ctx)
        # No pdfplumber call should be needed; returns empty early
        result = p._select_candidates()
        assert result == []

    def test_pdfplumber_error_returns_empty(self):
        p = self._parser()
        with patch("pdfplumber.open", side_effect=Exception("corrupt PDF")):
            result = p._select_candidates()
        assert result == []


# =============================================================================
# _render_page
# =============================================================================


class TestRenderPage:
    def test_calls_convert_from_path_with_correct_pages(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=_make_client(),
            dpi=150,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        with patch(
            "pdf2image.convert_from_path", return_value=[fake_image]
        ) as mock_convert:
            p._render_page(4)  # 0-based page 4 → 1-based page 5

        mock_convert.assert_called_once_with(
            "/tmp/fake.pdf",
            dpi=150,
            first_page=5,
            last_page=5,
        )

    def test_returns_bytes(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=_make_client(),
        )
        # Make save() write something to the BytesIO buffer
        def fake_save(buf, format):  # noqa: A002
            buf.write(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

        fake_image = MagicMock()
        fake_image.save = fake_save

        with patch("pdf2image.convert_from_path", return_value=[fake_image]):
            result = p._render_page(0)

        assert isinstance(result, bytes)
        assert result.startswith(b"\x89PNG")


# =============================================================================
# _vision_extract
# =============================================================================


class TestVisionExtract:
    def _parser(self, client):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        return IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=client,
        )

    def test_returns_none_on_match_false(self):
        client = _make_client({"match": False})
        p = self._parser(client)
        result = asyncio.run(p._vision_extract(0, b"fakepng"))
        assert result is None

    def test_returns_dict_on_match(self):
        client = _make_client(
            {
                "approved_budget_kes": 5_000_000,
                "released_kes": 3_000_000,
                "absorbed_kes": 2_500_000,
                "absorption_rate_pct": 50.0,
                "reporting_period": "Q2 2023/2024",
                "page_label": "1073 - Primary Health",
            }
        )
        p = self._parser(client)
        result = asyncio.run(p._vision_extract(3, b"fakepng"))
        assert result is not None
        assert result["budget_allocated_kes"] == 5_000_000
        assert result["budget_released_kes"] == 3_000_000
        assert result["extraction_page"] == 3
        assert result["match_method"] == "openai_vision_gpt4o"
        assert result["confidence_score"] == 90

    def test_returns_none_on_invalid_json(self):
        message = SimpleNamespace(content="this is not json {{{{")
        choice = SimpleNamespace(message=message)
        completion = SimpleNamespace(choices=[choice])

        async def bad_create(**kwargs):
            return completion

        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=bad_create)
        p = self._parser(client)
        result = asyncio.run(p._vision_extract(0, b"fakepng"))
        assert result is None

    def test_passes_base64_image_in_request(self):
        import base64

        calls = []

        async def capturing_create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"match": false}')
                    )
                ]
            )

        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=capturing_create)
        p = self._parser(client)
        img_bytes = b"\x89PNG\r\n"
        asyncio.run(p._vision_extract(0, img_bytes))

        assert len(calls) == 1
        messages = calls[0]["messages"]
        image_url_block = messages[0]["content"][1]
        assert image_url_block["type"] == "image_url"
        encoded = base64.b64encode(img_bytes).decode()
        assert encoded in image_url_block["image_url"]["url"]


# =============================================================================
# _to_financial_record
# =============================================================================


class TestToFinancialRecord:
    def _parser(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        return IntelligentCoBParser(
            pdf_path="/data/cob_q2.pdf",
            ctx=_make_ctx(
                canonical_name="Marsabit HC",
                ministry="Ministry of Health",
                vote_head="1073",
                fiscal_years=["2023/2024"],
                county="Marsabit",
            ),
            openai_client=_make_client(),
        )

    def test_full_mapping(self):
        p = self._parser()
        raw = {
            "approved_budget_kes": 10_000_000,
            "released_kes": 8_000_000,
            "absorbed_kes": 7_500_000,
            "absorption_rate_pct": 75.0,
            "reporting_period": "Q1 2023/2024",
            "page_label": "Primary Health Infrastructure",
        }
        rec = p._to_financial_record(raw, page_num=12)
        assert rec["source_system"] == "COB"
        assert rec["fiscal_year"] == "2023/2024"
        assert rec["ministry"] == "Ministry of Health"
        assert rec["vote_head"] == "1073"
        assert rec["programme"] == "Primary Health Infrastructure"
        assert rec["budget_allocated_kes"] == 10_000_000
        assert rec["budget_released_kes"] == 8_000_000
        assert rec["budget_absorbed_kes"] == 7_500_000
        assert rec["absorption_rate"] == 75.0
        assert rec["reporting_period"] == "Q1 2023/2024"
        assert rec["document_source"] == "/data/cob_q2.pdf"
        assert rec["match_method"] == "openai_vision_gpt4o"
        assert rec["confidence_score"] == 90
        assert rec["extraction_page"] == 12

    def test_fiscal_year_taken_from_context(self):
        p = self._parser()
        rec = p._to_financial_record({}, page_num=0)
        assert rec["fiscal_year"] == "2023/2024"

    def test_fiscal_year_none_when_context_empty(self):
        from data.context import ProjectContext
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=ProjectContext(),
            openai_client=_make_client(),
        )
        rec = p._to_financial_record({}, page_num=0)
        assert rec["fiscal_year"] is None


# =============================================================================
# _build_prompt
# =============================================================================


class TestBuildPrompt:
    def test_prompt_contains_canonical_name(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=_make_client(),
        )
        prompt = p._build_prompt()
        assert "Rural Health Centre Marsabit" in prompt

    def test_prompt_contains_fiscal_year(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(fiscal_years=["2024/2025"]),
            openai_client=_make_client(),
        )
        prompt = p._build_prompt()
        assert "2024/2025" in prompt

    def test_prompt_contains_all_ctx_fields(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=_make_client(),
        )
        prompt = p._build_prompt()
        assert "Ministry of Health" in prompt
        assert "Marsabit" in prompt
        assert "1073" in prompt


# =============================================================================
# extract() — full integration
# =============================================================================


class TestExtract:
    def _make_pdfplumber_mock(self, pages_text):
        pages = []
        for text in pages_text:
            page = MagicMock()
            page.extract_text.return_value = text
            pages.append(page)
        pdf_mock = MagicMock()
        pdf_mock.__enter__ = MagicMock(return_value=pdf_mock)
        pdf_mock.__exit__ = MagicMock(return_value=False)
        pdf_mock.pages = pages
        return pdf_mock

    def test_returns_empty_when_no_candidates(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=_make_client(),
        )
        with patch(
            "pdfplumber.open",
            return_value=self._make_pdfplumber_mock(["unrelated"] * 3),
        ):
            result = asyncio.run(p.extract())
        assert result == []

    def test_skips_no_match_pages(self):
        """Pages returning {"match": false} must not appear in results."""
        from data.parsers.intelligent_cob import IntelligentCoBParser

        # Stage 1: one matching page
        pages_text = ["Ministry of Health marsabit 1073"]

        # Stage 2: model says no match
        client = _make_client({"match": False})
        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=client,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        with patch(
            "pdfplumber.open",
            return_value=self._make_pdfplumber_mock(pages_text),
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            result = asyncio.run(p.extract())

        assert result == []

    def test_returns_records_for_matched_pages(self):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        pages_text = ["Ministry of Health marsabit 1073"]
        vision_response = {
            "approved_budget_kes": 5_000_000,
            "released_kes": 4_000_000,
            "absorbed_kes": 3_500_000,
            "absorption_rate_pct": 70.0,
            "reporting_period": "Q3 2023/2024",
            "page_label": "Vote 1073",
        }
        client = _make_client(vision_response)
        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=client,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        with patch(
            "pdfplumber.open",
            return_value=self._make_pdfplumber_mock(pages_text),
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            result = asyncio.run(p.extract())

        assert len(result) == 1
        assert result[0]["budget_allocated_kes"] == 5_000_000
        assert result[0]["source_system"] == "COB"

    def test_respects_max_vision_pages(self):
        """Only the top max_vision_pages candidates should be sent to Vision."""
        from data.parsers.intelligent_cob import IntelligentCoBParser

        # Create 5 matching pages but limit Vision calls to 2
        pages_text = ["Ministry of Health marsabit 1073"] * 5
        client = _make_client({"match": False})
        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=client,
            max_vision_pages=2,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        with patch(
            "pdfplumber.open",
            return_value=self._make_pdfplumber_mock(pages_text),
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        # Vision was called at most max_vision_pages times
        assert client.chat.completions.create.call_count <= 2

    def test_render_error_skips_page_gracefully(self):
        """A rendering failure on one page should not abort the whole extract."""
        from data.parsers.intelligent_cob import IntelligentCoBParser

        pages_text = [
            "Ministry of Health marsabit 1073",
            "marsabit health centre vote",
        ]
        client = _make_client({"match": False})
        p = IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=client,
        )
        with patch(
            "pdfplumber.open",
            return_value=self._make_pdfplumber_mock(pages_text),
        ), patch(
            "pdf2image.convert_from_path",
            side_effect=Exception("poppler not found"),
        ):
            # Should complete without raising
            result = asyncio.run(p.extract())
        assert result == []


# =============================================================================
# Sprint 5 — Vision cost guardrails
# =============================================================================


def _make_client_with_usage(
    response_json: dict,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
):
    """
    Return a fake AsyncOpenAI client whose completion response includes
    a .usage object so cost accumulation can be tested.
    """
    content = json.dumps(response_json)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    completion = SimpleNamespace(choices=[choice], usage=usage)

    async def fake_create(**kwargs):
        return completion

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=fake_create)
    return client


class TestVisionCostGuardrails:
    """Sprint 5 — per-investigation Vision API cost tracking and capping."""

    def _parser(self, client, cost_limit_usd=None, max_vision_pages=20):
        from data.parsers.intelligent_cob import IntelligentCoBParser

        return IntelligentCoBParser(
            pdf_path="/tmp/fake.pdf",
            ctx=_make_ctx(),
            openai_client=client,
            max_vision_pages=max_vision_pages,
            cost_limit_usd=cost_limit_usd,
        )

    def _fake_pdf(self, pages_text):
        pages = []
        for text in pages_text:
            page = MagicMock()
            page.extract_text.return_value = text
            pages.append(page)
        pdf_mock = MagicMock()
        pdf_mock.__enter__ = MagicMock(return_value=pdf_mock)
        pdf_mock.__exit__ = MagicMock(return_value=False)
        pdf_mock.pages = pages
        return pdf_mock

    def test_cost_starts_at_zero(self):
        """Parser initialises with zero cost and zero pages processed."""
        p = self._parser(_make_client({"match": False}))
        assert p.total_cost_usd == 0.0
        assert p.pages_processed == 0

    def test_cost_accumulates_per_page(self):
        """
        Each Vision call adds (prompt_tokens * input_rate + completion_tokens
        * output_rate) to total_cost_usd.

        1 000 000 prompt tokens × $5/1M + 0 completion = $5.00 per call.
        """
        # One matching candidate page
        pages_text = ["Ministry of Health marsabit 1073"]
        client = _make_client_with_usage(
            {"match": False},
            prompt_tokens=1_000_000,
            completion_tokens=0,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        assert p.pages_processed == 1
        # $5.00 input cost for 1M tokens
        assert abs(p.total_cost_usd - 5.0) < 1e-9

    def test_cost_accumulates_output_tokens(self):
        """Output tokens are charged at $15/1M."""
        pages_text = ["Ministry of Health marsabit 1073"]
        client = _make_client_with_usage(
            {"match": False},
            prompt_tokens=0,
            completion_tokens=1_000_000,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        # $15.00 output cost for 1M tokens
        assert abs(p.total_cost_usd - 15.0) < 1e-9

    def test_cost_limit_stops_pagination(self):
        """
        When total_cost_usd >= cost_limit_usd, no further Vision calls are made.

        3 candidate pages exist. First call costs $5 (1M prompt tokens).
        Limit = $3. After first call: $5 >= $3 → pages 2 and 3 not sent.
        Vision should be called exactly once.
        """
        pages_text = ["Ministry of Health marsabit 1073"] * 3
        client = _make_client_with_usage(
            {"match": False},
            prompt_tokens=1_000_000,
            completion_tokens=0,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client, cost_limit_usd=3.0)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        # Only the first page reached Vision; the remaining two were blocked
        assert client.chat.completions.create.call_count == 1
        assert p.pages_processed == 1

    def test_zero_cost_limit_blocks_all_vision_calls(self):
        """cost_limit_usd=0.0 means no Vision calls are issued at all."""
        pages_text = ["Ministry of Health marsabit 1073"] * 2
        client = _make_client_with_usage({"match": False})
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client, cost_limit_usd=0.0)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            result = asyncio.run(p.extract())

        client.chat.completions.create.assert_not_called()
        assert result == []

    def test_no_limit_processes_all_pages(self):
        """cost_limit_usd=None (default) → all candidate pages are processed."""
        pages_text = ["Ministry of Health marsabit 1073"] * 3
        # Each call: 0 tokens → $0 cost, will never trigger limit
        client = _make_client_with_usage({"match": False}, prompt_tokens=0)
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client, cost_limit_usd=None, max_vision_pages=10)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        assert client.chat.completions.create.call_count == 3
        assert p.pages_processed == 3

    def test_cost_exposed_after_extract(self):
        """total_cost_usd is readable on the parser instance after extract()."""
        pages_text = ["Ministry of Health marsabit 1073"]
        client = _make_client_with_usage(
            {"match": False},
            prompt_tokens=200_000,
            completion_tokens=0,
        )
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        # 200k tokens × $5/1M = $1.00
        assert abs(p.total_cost_usd - 1.0) < 1e-9

    def test_no_usage_in_response_leaves_cost_zero(self):
        """If the API response has no .usage, cost stays at 0 (graceful)."""
        pages_text = ["Ministry of Health marsabit 1073"]
        # _make_client (no usage) — SimpleNamespace without .usage attr
        client = _make_client({"match": False})
        fake_image = MagicMock()
        fake_image.save = MagicMock()

        p = self._parser(client)
        with patch(
            "pdfplumber.open", return_value=self._fake_pdf(pages_text)
        ), patch("pdf2image.convert_from_path", return_value=[fake_image]):
            asyncio.run(p.extract())

        # No usage on response → cost stays at 0
        assert p.total_cost_usd == 0.0
        assert p.pages_processed == 1
