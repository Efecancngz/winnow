from pathlib import Path

from junitparser import Error, Failure, JUnitXml, TestSuite

from winnow.ingest.base import TestResultParser
from winnow.ingest.models import TestOutcome


class JUnitParser(TestResultParser):
    def parse(self, report_path: Path) -> list[TestOutcome]:
        xml = JUnitXml.fromfile(str(report_path))
        if isinstance(xml, TestSuite):
            xml = [xml]

        outcomes: list[TestOutcome] = []
        for suite in xml:
            for case in suite:
                case_id = f"{case.classname}.{case.name}"
                passed = not any(isinstance(r, (Failure, Error)) for r in case.result)
                outcomes.append(
                    TestOutcome(
                        case_id=case_id,
                        passed=passed,
                        duration_seconds=case.time or 0.0,
                    )
                )
        return outcomes
