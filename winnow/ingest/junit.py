from pathlib import Path

from junitparser import JUnitXml

from winnow.ingest.base import TestResultParser
from winnow.ingest.models import TestOutcome


class JUnitParser(TestResultParser):
    def parse(self, report_path: Path) -> list[TestOutcome]:
        xml = JUnitXml.fromfile(str(report_path))

        outcomes: list[TestOutcome] = []
        for suite in xml:
            for case in suite:
                test_id = f"{case.classname}.{case.name}"
                passed = len(case.result) == 0
                outcomes.append(
                    TestOutcome(
                        test_id=test_id,
                        passed=passed,
                        duration_seconds=case.time or 0.0,
                    )
                )
        return outcomes
