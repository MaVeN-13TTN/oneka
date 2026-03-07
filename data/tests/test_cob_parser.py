"""Tests for data/parsers/cob.py — COB BIRR PDF parser."""

from unittest.mock import MagicMock, patch

import pytest


class TestCoBParserExtractTables:

    def test_extract_tables_returns_dataframes(self):
        from data.parsers.cob import CoBParser

        mock_page = MagicMock()
        mock_page.extract_tables.return_value = [
            [["Vote", "Approved Budget", "Expenditure"], ["Health", "1,000,000", "800,000"]],
        ]

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("data.parsers.cob.pdfplumber.open", return_value=mock_pdf):
            parser = CoBParser("/fake/path.pdf")
            tables = parser.extract_tables()

        assert len(tables) == 1
        assert list(tables[0].columns) == ["Vote", "Approved Budget", "Expenditure"]
        assert tables[0].iloc[0]["Vote"] == "Health"

    def test_extract_tables_skips_single_row_tables(self):
        from data.parsers.cob import CoBParser

        mock_page = MagicMock()
        mock_page.extract_tables.return_value = [
            [["Header Only"]],  # Single row — no data
        ]
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("data.parsers.cob.pdfplumber.open", return_value=mock_pdf):
            parser = CoBParser("/fake/path.pdf")
            tables = parser.extract_tables()

        assert len(tables) == 0

    def test_extract_tables_handles_pdf_error(self):
        from data.parsers.cob import CoBParser

        with patch("data.parsers.cob.pdfplumber.open", side_effect=Exception("corrupt")):
            parser = CoBParser("/bad.pdf")
            tables = parser.extract_tables()

        assert tables == []

    def test_extract_tables_handles_none_header(self):
        """None header cells get replaced with col_N placeholder."""
        from data.parsers.cob import CoBParser

        mock_page = MagicMock()
        mock_page.extract_tables.return_value = [
            [[None, "Budget", None], ["Row1", "100", "50"]],
        ]
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("data.parsers.cob.pdfplumber.open", return_value=mock_pdf):
            parser = CoBParser("/fake/path.pdf")
            tables = parser.extract_tables()

        assert "col_0" in tables[0].columns
        assert "Budget" in tables[0].columns
        assert "col_2" in tables[0].columns


class TestCoBParserFindExpenditureTable:

    def _make_parser_with_tables(self, tables_data):
        from data.parsers.cob import CoBParser

        parser = CoBParser("/fake.pdf")
        with patch.object(parser, "extract_tables", return_value=tables_data):
            return parser.find_expenditure_table()

    def test_finds_table_with_matching_keywords(self):
        import pandas as pd

        df = pd.DataFrame(
            {"Vote": ["Health"], "Approved Budget": ["1000"], "Expenditure": ["800"]}
        )
        result = self._make_parser_with_tables([df])
        assert result is not None
        assert "Vote" in result.columns

    def test_returns_none_when_no_match(self):
        import pandas as pd

        df = pd.DataFrame({"Name": ["Alice"], "Age": ["30"]})
        result = self._make_parser_with_tables([df])
        assert result is None

    def test_requires_at_least_two_keyword_matches(self):
        import pandas as pd

        # Only one keyword match — should not be selected
        df = pd.DataFrame({"Vote": ["Health"], "Amount": ["1000"]})
        result = self._make_parser_with_tables([df])
        assert result is None


class TestCoBParserExtractFinancialRecords:

    def test_extract_records_with_fuzzy_match(self):
        import pandas as pd
        from data.parsers.cob import CoBParser

        df = pd.DataFrame({
            "Vote": ["Ministry of Health", "Ministry of Education", "Roads Authority"],
            "Approved Budget": ["1,000,000", "2,000,000", "3,000,000"],
            "Expenditure": ["800,000", "1,500,000", "2,900,000"],
        })

        parser = CoBParser("/fake.pdf")
        with patch.object(parser, "find_expenditure_table", return_value=df):
            records = parser.extract_financial_records(
                project_name="Health Ministry",
                fiscal_year="2023/2024",
                pdf_url="https://cob.go.ke/report.pdf",
            )

        assert len(records) >= 1
        rec = records[0]
        assert rec["source_system"] == "COB"
        assert rec["fiscal_year"] == "2023/2024"
        assert rec["match_method"] == "rapidfuzz_token_set_ratio"
        assert rec["budget_allocated_kes"] == 1000000.0
        assert rec["budget_absorbed_kes"] == 800000.0
        assert rec["document_source"] == "https://cob.go.ke/report.pdf"
        assert rec["confidence_score"] > 0

    def test_extract_records_computes_absorption_rate(self):
        import pandas as pd
        from data.parsers.cob import CoBParser

        df = pd.DataFrame({
            "Programme": ["Water Supply Project"],
            "Allocated": ["500,000"],
            "Actual": ["250,000"],
        })

        parser = CoBParser("/fake.pdf")
        with patch.object(parser, "find_expenditure_table", return_value=df):
            records = parser.extract_financial_records("Water Supply", "2023/2024", "url")

        assert len(records) == 1
        assert records[0]["absorption_rate"] == 50.0

    def test_extract_records_returns_empty_when_no_table(self):
        from data.parsers.cob import CoBParser

        parser = CoBParser("/fake.pdf")
        with patch.object(parser, "find_expenditure_table", return_value=None):
            records = parser.extract_financial_records("Test", "2023/2024", "url")

        assert records == []

    def test_to_decimal_handles_various_formats(self):
        """Test the internal _to_decimal helper via extract_financial_records."""
        import pandas as pd
        from data.parsers.cob import CoBParser

        df = pd.DataFrame({
            "Vote": ["Test Project"],
            "Budget": ["1,234,567.89"],
            "Expenditure": ["50%"],
        })

        parser = CoBParser("/fake.pdf")
        with patch.object(parser, "find_expenditure_table", return_value=df):
            records = parser.extract_financial_records("Test Project", "2024", "url")

        assert len(records) == 1
        assert records[0]["budget_allocated_kes"] == 1234567.89
