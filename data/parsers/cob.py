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
