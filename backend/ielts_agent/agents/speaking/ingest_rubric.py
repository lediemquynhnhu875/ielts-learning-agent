"""Reproducible official PDF ingestion; run: python -m speaking.ingest_rubric.

PDF/corpus stay in .cache, not redistributed as open-licensed project content.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from ielts_agent.agents.speaking.rag import DEFAULT_CORPUS, SOURCE_URL

FALLBACK_URL = "https://ielts.org/cdn/ielts-guides/ielts-speaking-band-descriptors.pdf"
CRITERIA = ("FC", "LR", "GRA", "PR")


def extract_pdf(path, source_url):
    import pdfplumber

    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    version = "official-speaking-" + sha[:16]
    rows = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for cells in table:
                    if len(cells) != 5 or not (cells[0] or "").strip().isdigit():
                        continue
                    band = int(cells[0].strip())
                    if not 0 <= band <= 9:
                        continue
                    for criterion, text in zip(CRITERIA, cells[1:]):
                        # Band 0 is a merged cell spanning all four columns.
                        if band == 0:
                            text = cells[1]
                        if not text or not text.strip():
                            raise ValueError(f"Missing {criterion} band {band} on page {page_no}")
                        rows.append({"chunk_id": f"ielts-speaking-{sha[:12]}-{criterion.lower()}-{band}",
                                     "test_part": "speaking", "criterion": criterion, "band": band,
                                     "text": " ".join(text.split()), "version": version, "source_url": source_url,
                                     "page": page_no, "source_sha256": sha,
                                     "publisher": "IELTS Partners (British Council, IDP, Cambridge)",
                                     "rights": "Copyright retained by IELTS Partners; not an open licence",
                                     "reference_url": "https://takeielts.britishcouncil.org/teach-ielts/test-information/assessment"})
    expected = {(c, b) for c in CRITERIA for b in range(10)}
    if {(r["criterion"], r["band"]) for r in rows} != expected or len(rows) != 40:
        raise ValueError("Unexpected PDF layout: require exactly 40 complete criterion/band chunks")
    return sorted(rows, key=lambda r: (r["criterion"], r["band"]))


def ingest(path=None, source_url=None, output=DEFAULT_CORPUS):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = output.parent / "official-speaking.pdf"
        for url in (SOURCE_URL, FALLBACK_URL):
            result = subprocess.run(["curl", "-fsSL", "--max-time", "20", url, "-o", str(path)], capture_output=True)
            if result.returncode == 0 and path.read_bytes().startswith(b"%PDF"):
                source_url = url
                break
        else:
            raise ValueError("Official download failed. Download PDF manually, then use --pdf and --source-url.")
    if source_url not in {SOURCE_URL, FALLBACK_URL}:
        raise ValueError("Use the exact official URL of the downloaded PDF")
    rows = extract_pdf(path, source_url)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    manifest = {"source_url": source_url, "british_council_pdf_url": SOURCE_URL,
                "fallback_used": source_url == FALLBACK_URL, "sha256": rows[0]["source_sha256"],
                "version": rows[0]["version"], "chunks": len(rows), "ingested_at": datetime.now(timezone.utc).isoformat(),
                "split": "one criterion × one band; preserve merged band 0", "rights": rows[0]["rights"]}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--source-url", choices=[SOURCE_URL, FALLBACK_URL])
    parser.add_argument("--output", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    print(json.dumps(ingest(args.pdf, args.source_url, args.output), ensure_ascii=False, indent=2))
