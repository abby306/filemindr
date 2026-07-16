"""Generate a small synthetic demo corpus of PDFs for quickstart and eval.

Creates fictional documents (invoice, receipt, NDA, spec, bank statement,
certificate, resume, project plan) under ``storage/samples/`` so a fresh
install can exercise the full pipeline without anyone's real documents:

    python -m scripts.make_demo_corpus
    python -m scripts.seed_corpus          # ingest through OCR → extraction → embedding

The gold eval set (``eval/gold/seed.yaml``) is written against these files.
All names, companies, and figures are invented.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz  # PyMuPDF

DOCS: dict[str, str] = {
    "acme_invoice.pdf": """INVOICE

Acme Web Services LLC
128 Harbor Street, Portland, OR

Bill to: Meridian Labs LLC
Invoice number: INV-2041
Date issued: 2026-07-01
Due date: 2026-08-15

Description: Website redesign and CMS migration, June 2026.
Line items: design sprint (USD 900.00), CMS migration (USD 740.00),
QA and launch support (USD 200.00).

Total amount due: USD 1840.00
Payment terms: Net 45. Pay by bank transfer to the account on file.
""",
    "blue_fern_receipt.pdf": """BLUE FERN CAFE
14 Alder Lane, Portland, OR
Receipt number: 55031
Date: 2026-06-12  10:42 AM

2x flat white           7.50
1x almond croissant     4.25
1x lunch special       12.00

Subtotal: 23.75
VAT (12%): 2.85
Total: 23.75
Paid by card (VISA ending 4421). Served by R. Ortiz. Thank you!
""",
    "meridian_nda.pdf": """MUTUAL NON-DISCLOSURE AGREEMENT

This Agreement is entered into between Meridian Labs LLC ("Disclosing
Party") and Alex Doe ("Receiving Party"), effective 2026-05-01.

1. Confidential Information includes source code, product designs,
business plans, and customer lists disclosed by either party.
2. The Receiving Party shall not disclose Confidential Information to
any third party without prior written consent.
3. This Agreement remains in effect for five years from the effective
date. Obligations regarding trade secrets survive termination.
4. Signed by Alex Doe and, for Meridian Labs LLC, by Jordan Vance
(Director of Operations) on 2026-05-01.
""",
    "orbit_spec.pdf": """ORBIT ASSET TRACKER — TECHNICAL SPECIFICATION v2.1

Orbit is a battery-powered asset tracker for warehouse equipment.

Hardware: ESP32-S3 microcontroller, LoRa radio, BLE 5.0, accelerometer.
Connectivity: telemetry is published over MQTT on port 1883 to the
fleet server; LoRaWAN fallback when WiFi is unavailable.
Power: 3400 mAh cell; expected battery life is 18 months at the default
15-minute reporting interval.
Firmware: version 2.1 adds over-the-air updates and deep-sleep wake on
motion. Enclosure is IP67 rated.
""",
    "harbor_statement.pdf": """HARBOR BANK — MONTHLY STATEMENT

Account holder: Doe Ventures LLC
Statement period: 2026-03-01 to 2026-03-31
Account number: ****7719

Opening balance: 9850.44
2026-03-04  Client payment received      +4200.00
2026-03-11  Office rent                   -1500.00
2026-03-18  Cloud hosting invoice          -320.25
2026-03-27  Software subscriptions         -200.00
Closing balance: 12430.19
""",
    "cert_data_engineering.pdf": """CERTIFICATE OF COMPLETION

This certifies that Alex Doe has successfully completed the online
course "Data Engineering Fundamentals" offered by Northgate Learning.

Date of completion: 2026-02-10
Instructor: Prof. Maria Rivera
Certificate ID: NG-88410
The course covered data pipelines, warehousing, and stream processing.
""",
    "alex_doe_resume.pdf": """ALEX DOE
Software Engineer — Portland, OR — alex.doe@example.com

Experience:
Northwind Systems (2024–present): backend engineer on the billing
platform; built usage metering for 2M daily events.
Meridian Labs (2022–2024): full-stack developer, internal tools.

Education: B.S. Computer Science, Cascade State University, GPA 3.80,
graduated 2022.
Skills: Python, TypeScript, PostgreSQL, distributed systems.
""",
    "garden_plan.pdf": """AUTOMATED GARDEN — PROJECT PLAN

Goal: a self-regulating indoor garden that learns watering schedules.

The prediction model uses an LSTM network trained on soil moisture,
temperature, and light readings sampled every 10 minutes.
Sample plants for the pilot are basil and thyme.
Hardware budget is capped at USD 500.00 (sensors, pump, controller).
Milestone 1: sensor rig assembled. Milestone 2: two weeks of clean
telemetry. Milestone 3: model-driven watering enabled.
""",
}


def make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, 558, 788), text, fontsize=11)
    doc.save(path)
    doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic demo corpus.")
    parser.add_argument(
        "--out", default="storage/samples", help="output directory (default: storage/samples)"
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in DOCS.items():
        make_pdf(out / name, text)
        print(f"  wrote {out / name}")
    print(f"\n{len(DOCS)} demo PDFs ready. Ingest them with: python -m scripts.seed_corpus")


if __name__ == "__main__":
    main()
