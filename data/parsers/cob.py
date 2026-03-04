import pdfplumber
import pandas as pd
from typing import List, Dict, Optional


class CoBParser:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def extract_tables(self) -> List[pd.DataFrame]:
        """
        Extracts all tables from the PDF.
        """
        tables = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                # Limit to first 50 pages for speed during testing
                pages = pdf.pages[:50] if len(pdf.pages) > 50 else pdf.pages
                for page in pages:
                    extracted = page.extract_tables()
                    for table in extracted:
                        # Basic assumption: Row 0 is header
                        if table and len(table) > 1:
                            # Clean headers
                            headers = [str(h).replace('\n', ' ').strip() if h else f"col_{i}" for i, h in enumerate(table[0])]
                            df = pd.DataFrame(table[1:], columns=headers)
                            tables.append(df)
        except Exception as e:
            print(f"Error parsing PDF {self.pdf_path}: {e}")
        return tables

    def find_expenditure_table(self) -> Optional[pd.DataFrame]:
        """
        Attempts to identify the expenditure table based on keywords.
        """
        target_keywords = ["Vote", "Approved Budget", "Expenditure", "Absorption"]
        tables = self.extract_tables()

        for df in tables:
            # Check if headers contain enough keywords
            matches = sum(1 for keyword in target_keywords if any(keyword.lower() in col.lower() for col in df.columns))
            if matches >= 2:
                return df
        return None

    def extract_financial_records(
        self,
        project_name: str,
        fiscal_year: str,
        pdf_url: str,
    ) -> List[Dict]:
        """
        Extracts FinancialRecord-compatible dicts from the expenditure table.

        Uses RapidFuzz token_set_ratio to match `project_name` against rows
        in the Vote column (score threshold: 60). Returns all rows above
        threshold, sorted by match score descending.

        Args:
            project_name: Project name to fuzzy-match against Vote column.
            fiscal_year:  Fiscal year string e.g. "2023/2024".
            pdf_url:      Source URL stored in document_source.

        Returns:
            List of dicts keyed to FinancialRecord column names.
        """
        df = self.find_expenditure_table()
        if df is None or df.empty:
            return []

        try:
            from rapidfuzz import process as fuzz_process, fuzz
        except ImportError:
            print("rapidfuzz not installed — pip install rapidfuzz")
            return []

        # Identify Vote column (may be labelled "Vote", "Vote Head", "Programme", etc.)
        vote_col = next(
            (col for col in df.columns if "vote" in col.lower() or "programme" in col.lower()),
            None,
        )
        if vote_col is None:
            return []

        # Identify financial amount columns by keyword
        def _find_col(keywords: list) -> Optional[str]:
            for kw in keywords:
                match = next((c for c in df.columns if kw.lower() in c.lower()), None)
                if match:
                    return match
            return None

        alloc_col = _find_col(["approved budget", "allocated", "budget"])
        absorbed_col = _find_col(["expenditure", "absorbed", "actual"])
        absorption_col = _find_col(["absorption", "absorption rate", "%"])

        def _to_decimal(val) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(str(val).replace(",", "").replace("%", "").strip())
            except (ValueError, TypeError):
                return None

        vote_values = df[vote_col].fillna("").astype(str).tolist()
        results = fuzz_process.extract(
            project_name,
            vote_values,
            scorer=fuzz.token_set_ratio,
            score_cutoff=60,
            limit=10,
        )

        records = []
        for matched_text, score, idx in results:
            row = df.iloc[idx]
            allocated = _to_decimal(row.get(alloc_col) if alloc_col else None)
            absorbed = _to_decimal(row.get(absorbed_col) if absorbed_col else None)
            absorption = _to_decimal(row.get(absorption_col) if absorption_col else None)

            # Compute absorption rate if not explicitly in a column
            if absorption is None and allocated and absorbed and allocated > 0:
                absorption = round((absorbed / allocated) * 100, 2)

            records.append(
                {
                    "source_system": "COB",
                    "fiscal_year": fiscal_year,
                    "vote_head": None,       # numeric vote head not always present
                    "ministry": matched_text,
                    "programme": matched_text,
                    "budget_allocated_kes": allocated,
                    "budget_absorbed_kes": absorbed,
                    "absorption_rate": absorption,
                    "reporting_period": fiscal_year,
                    "document_source": pdf_url,
                    "match_method": "rapidfuzz_token_set_ratio",
                    "confidence_score": int(score),
                }
            )

        return records
