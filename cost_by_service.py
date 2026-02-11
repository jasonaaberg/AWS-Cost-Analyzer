#!/usr/bin/env python3
import argparse
import csv
import os
import sys

from cost_analyzer import (
    load_sheet_config,
    store_sheet_config,
    upload_csv_to_google_sheet,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarize AWS costs by service and export to CSV."
    )
    parser.add_argument(
        "--input",
        default="aws_costs.csv",
        help="Input CSV filename (default: aws_costs.csv).",
    )
    parser.add_argument(
        "--output",
        default="cost_by_service.csv",
        help="Output CSV filename (default: cost_by_service.csv).",
    )
    parser.add_argument(
        "--gcp-key",
        default="key.json",
        help="Path to Google service account JSON key file.",
    )
    parser.add_argument(
        "--sheet-config",
        default="sheet_config.json",
        help="Path to a JSON file that stores the Google Sheet ID/tab.",
    )
    parser.add_argument(
        "--sheet-tab",
        default="cost_by_service",
        help="Google Sheet tab name to write data into (default: cost_by_service).",
    )
    return parser.parse_args()


def load_costs(input_path):
    if not os.path.exists(input_path):
        print(f"Error: Input CSV not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    totals = {}
    unit = "USD"

    with open(input_path, "r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            service = (row.get("service") or "").strip() or "Uncategorized"
            amount_str = (row.get("amount") or "0").strip()
            row_unit = (row.get("unit") or "").strip()
            if row_unit:
                unit = row_unit

            try:
                amount = float(amount_str)
            except ValueError:
                amount = 0.0

            totals[service] = totals.get(service, 0.0) + amount

    return totals, unit


def write_summary(output_path, totals, unit):
    sorted_rows = sorted(
        totals.items(), key=lambda item: item[1], reverse=True
    )

    currency_prefix = "$" if unit == "USD" else ""

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["service", "total_amount", "unit"])
        for service, amount in sorted_rows:
            formatted_amount = f"{currency_prefix}{amount:,.2f}"
            writer.writerow([service, formatted_amount, unit])


def main():
    args = parse_args()
    totals, unit = load_costs(args.input)

    if not totals:
        print("No cost data found to aggregate.")
        return

    write_summary(args.output, totals, unit)
    print(f"Wrote cost summary to {args.output}")

    sheet_id, sheet_tab = load_sheet_config("", args.sheet_tab, args.sheet_config)

    if args.gcp_key and os.path.exists(args.gcp_key):
        sheet_id, sheet_url = upload_csv_to_google_sheet(
            args.output,
            args.gcp_key,
            sheet_id=sheet_id,
            sheet_tab=sheet_tab,
        )
        store_sheet_config(args.sheet_config, sheet_id, sheet_tab)
        print(f"Uploaded to Google Sheet: {sheet_url}")
    else:
        print(
            "Google Sheets upload skipped (missing key file). "
            "Provide --gcp-key or place key.json in the project directory."
        )


if __name__ == "__main__":
    main()
