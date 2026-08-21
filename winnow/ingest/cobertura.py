import xml.etree.ElementTree as ET
from pathlib import Path

from winnow.ingest.base import CoverageParser
from winnow.ingest.models import CoverageReport, FileCoverage


class CoberturaParser(CoverageParser):
    def parse(self, report_path: Path) -> CoverageReport:
        tree = ET.parse(report_path)
        root = tree.getroot()

        files: dict[str, set[int]] = {}
        for class_el in root.iter("class"):
            filename = class_el.get("filename")
            if filename is None:
                continue
            covered = files.setdefault(filename, set())
            lines_el = class_el.find("lines")
            if lines_el is None:
                continue
            for line_el in lines_el.findall("line"):
                hits = int(line_el.get("hits", "0"))
                if hits > 0:
                    covered.add(int(line_el.get("number")))

        return CoverageReport(
            files=tuple(
                FileCoverage(file_path=path, covered_lines=frozenset(lines))
                for path, lines in files.items()
            )
        )
