from abc import ABC, abstractmethod
from pathlib import Path

from winnow.ingest.models import CoverageReport, TestOutcome


class CoverageParser(ABC):
    @abstractmethod
    def parse(self, report_path: Path) -> CoverageReport:
        """Parse a coverage report file into a normalized CoverageReport."""


class TestResultParser(ABC):
    @abstractmethod
    def parse(self, report_path: Path) -> list[TestOutcome]:
        """Parse a test result report file into normalized TestOutcomes."""
