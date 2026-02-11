#!/usr/bin/env python3
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from google.oauth2 import service_account
from googleapiclient.discovery import build


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export AWS Cost Explorer data to CSV."
    )
    parser.add_argument(
        "--config",
        default="aws_accounts.json",
        help="Path to AWS accounts configuration file (default: aws_accounts.json).",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for Cost Explorer (default: us-east-1).",
    )
    parser.add_argument(
        "--start-date",
        help="Start date in YYYY-MM-DD (default: 30 days ago).",
    )
    parser.add_argument(
        "--end-date",
        help="End date in YYYY-MM-DD (default: today, exclusive).",
    )
    parser.add_argument(
        "--granularity",
        default="DAILY",
        choices=["DAILY", "MONTHLY"],
        help="Granularity of cost data (default: DAILY).",
    )
    parser.add_argument(
        "--group-by",
        default="SERVICE",
        choices=["SERVICE", "NONE"],
        help="Group costs by service or return totals (default: SERVICE).",
    )
    parser.add_argument(
        "--output",
        default="aws_costs.csv",
        help="Output CSV file name (default: aws_costs.csv).",
    )
    parser.add_argument(
        "--gcp-key",
        default="key.json",
        help="Path to Google service account JSON key file.",
    )
    parser.add_argument(
        "--sheet-id",
        default="",
        help="Google Sheet ID to update (if omitted, a new sheet is created).",
    )
    parser.add_argument(
        "--sheet-config",
        default="sheet_config.json",
        help=(
            "Path to a JSON file that stores the Google Sheet ID/tab "
            "(default: sheet_config.json)."
        ),
    )
    parser.add_argument(
        "--sheet-tab",
        default="raw_data",
        help="Google Sheet tab name to write data into (default: raw_data).",
    )
    parser.add_argument(
        "--sheet-title",
        default="AWS Cost Analyzer",
        help="Title for a new Google Sheet (default: AWS Cost Analyzer).",
    )
    parser.add_argument(
        "--share-with",
        help="Email address to grant edit access to the Google Sheet.",
    )
    return parser.parse_args()


def default_dates(start_str, end_str):
    if start_str and end_str:
        return start_str, end_str

    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    if start_str:
        start_date = date.fromisoformat(start_str)
    if end_str:
        end_date = date.fromisoformat(end_str)

    return start_date.isoformat(), end_date.isoformat()


def load_aws_accounts(config_path):
    if not os.path.exists(config_path):
        print(
            f"Error: AWS accounts config file not found: {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config.get("accounts", [])


def get_account_info(iam_client, sts_client):
    account_id = ""
    account_name = ""
    try:
        identity = sts_client.get_caller_identity()
        account_id = identity.get("Account", "")
    except (BotoCoreError, ClientError):
        account_id = ""

    try:
        aliases = iam_client.list_account_aliases().get("AccountAliases", [])
        if aliases:
            account_name = aliases[0]
    except (BotoCoreError, ClientError):
        account_name = ""

    return account_id, account_name


def upload_csv_to_google_sheet(
    csv_path,
    gcp_key_path,
    sheet_id=None,
    sheet_title="AWS Cost Analyzer",
    sheet_tab="Sheet1",
    share_with=None,
):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = service_account.Credentials.from_service_account_file(
        gcp_key_path, scopes=scopes
    )
    sheets_service = build("sheets", "v4", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    if not sheet_id:
        spreadsheet = (
            sheets_service.spreadsheets()
            .create(body={"properties": {"title": sheet_title}})
            .execute()
        )
        sheet_id = spreadsheet.get("spreadsheetId")

    sheet_tab = ensure_sheet_tab(sheets_service, sheet_id, sheet_tab)

    with open(csv_path, "r", encoding="utf-8") as csvfile:
        rows = list(csv.reader(csvfile))

    sheets_service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=sheet_tab,
    ).execute()

    (
        sheets_service.spreadsheets()
        .values()
        .update(
            spreadsheetId=sheet_id,
            range=f"{sheet_tab}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        )
        .execute()
    )

    if share_with:
        drive_service.permissions().create(
            fileId=sheet_id,
            body={"type": "user", "role": "writer", "emailAddress": share_with},
            sendNotificationEmail=True,
        ).execute()

    return sheet_id, f"https://docs.google.com/spreadsheets/d/{sheet_id}"


def ensure_sheet_tab(sheets_service, sheet_id, sheet_tab):
    if not sheet_tab:
        sheet_tab = "Sheet1"

    spreadsheet = sheets_service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets(properties(sheetId,title))",
    ).execute()
    for sheet in spreadsheet.get("sheets", []):
        title = sheet.get("properties", {}).get("title")
        if title == sheet_tab:
            return sheet_tab

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_tab}}}]},
    ).execute()

    return sheet_tab


def load_sheet_config(explicit_sheet_id, explicit_sheet_tab, sheet_config_path):
    sheet_id = explicit_sheet_id or ""
    sheet_tab = explicit_sheet_tab or ""

    if sheet_config_path and os.path.exists(sheet_config_path):
        with open(sheet_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not sheet_id:
            sheet_id = config.get("sheet_id", "").strip()
        if not sheet_tab:
            sheet_tab = config.get("sheet_tab", "").strip()
        if not sheet_id and not sheet_tab:
            print(
                f"Warning: {sheet_config_path} is empty. "
                "Provide a sheet_id or sheet_tab, or pass flags explicitly.",
                file=sys.stderr,
            )
    elif sheet_config_path:
        print(
            f"Warning: sheet config file not found: {sheet_config_path}",
            file=sys.stderr,
        )

    if not sheet_tab:
        sheet_tab = "Sheet1"

    return sheet_id, sheet_tab


def store_sheet_config(sheet_config_path, sheet_id, sheet_tab):
    if not sheet_config_path:
        return

    with open(sheet_config_path, "w", encoding="utf-8") as f:
        payload = {}
        if sheet_id:
            payload["sheet_id"] = sheet_id
        if sheet_tab:
            payload["sheet_tab"] = sheet_tab
        json.dump(payload, f, indent=2)
        f.write("\n")


def fetch_costs(
    ce_client,
    start_date,
    end_date,
    granularity,
    group_by,
):
    request = {
        "TimePeriod": {"Start": start_date, "End": end_date},
        "Granularity": granularity,
        "Metrics": ["UnblendedCost"],
    }

    if group_by == "SERVICE":
        request["GroupBy"] = [
            {"Type": "DIMENSION", "Key": "SERVICE"}
        ]

    results = []
    next_token = None
    while True:
        if next_token:
            request["NextPageToken"] = next_token
        elif "NextPageToken" in request:
            del request["NextPageToken"]

        response = ce_client.get_cost_and_usage(**request)
        results.extend(response.get("ResultsByTime", []))
        next_token = response.get("NextPageToken")
        if not next_token:
            break

    return results


def process_account(account_config, region, start_date, end_date, granularity, group_by):
    aws_access_key_id = account_config.get("aws_access_key_id")
    aws_secret_access_key = account_config.get("aws_secret_access_key")
    account_region = account_config.get("region", region)

    if not aws_access_key_id or not aws_secret_access_key:
        print("Warning: Skipping account - missing credentials", file=sys.stderr)
        return []

    session = boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=account_region,
    )

    ce_client = session.client("ce", region_name=region)
    iam_client = session.client("iam")
    sts_client = session.client("sts")

    account_id, account_name = get_account_info(iam_client, sts_client)

    results = fetch_costs(
        ce_client,
        start_date,
        end_date,
        granularity,
        group_by,
    )

    rows = []
    for period in results:
        period_start = period.get("TimePeriod", {}).get("Start", "")
        period_end = period.get("TimePeriod", {}).get("End", "")

        if group_by == "SERVICE":
            for group in period.get("Groups", []):
                keys = group.get("Keys", [])
                service_name = keys[0] if keys else ""
                metric = group.get("Metrics", {}).get("UnblendedCost", {})
                amount = metric.get("Amount", "0")
                unit = metric.get("Unit", "USD")
                rows.append(
                    [
                        account_id,
                        account_name,
                        period_start,
                        period_end,
                        granularity,
                        service_name,
                        amount,
                        unit,
                    ]
                )
        else:
            metric = period.get("Total", {}).get("UnblendedCost", {})
            amount = metric.get("Amount", "0")
            unit = metric.get("Unit", "USD")
            rows.append(
                [
                    account_id,
                    account_name,
                    period_start,
                    period_end,
                    granularity,
                    "",
                    amount,
                    unit,
                ]
            )

    print(
        f"Fetched {len(rows)} rows for account {account_id or 'unknown'} ({account_name or 'no-alias'})"
    )
    return rows


def main():
    args = parse_args()
    run_started_at = datetime.now(timezone.utc)
    start_date, end_date = default_dates(args.start_date, args.end_date)
    sheet_id, sheet_tab = load_sheet_config(
        args.sheet_id, args.sheet_tab, args.sheet_config
    )

    accounts = load_aws_accounts(args.config)
    if not accounts:
        print("Error: No AWS accounts configured in config file", file=sys.stderr)
        sys.exit(1)

    total_rows = 0
    with open(args.output, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "account_id",
                "account_name",
                "period_start",
                "period_end",
                "granularity",
                "service",
                "amount",
                "unit",
            ]
        )

        for account_config in accounts:
            rows = process_account(
                account_config,
                args.region,
                start_date,
                end_date,
                args.granularity,
                args.group_by,
            )
            for row in rows:
                writer.writerow(row)
            total_rows += len(rows)

    print(f"Wrote {total_rows} rows to {args.output}")

    if args.gcp_key and os.path.exists(args.gcp_key):
        sheet_id, sheet_url = upload_csv_to_google_sheet(
            args.output,
            args.gcp_key,
            sheet_id=sheet_id,
            sheet_title=args.sheet_title,
            sheet_tab=sheet_tab,
            share_with=args.share_with,
        )
        print(f"Uploaded to Google Sheet: {sheet_url}")
    else:
        print(
            "Google Sheets upload skipped (missing key file). "
            "Provide --gcp-key or place key.json in the project directory."
        )

    result = subprocess.run([sys.executable, "cost_by_service.py"], check=False)
    if result.returncode != 0:
        print("Error: cost_by_service.py failed.", file=sys.stderr)
        sys.exit(result.returncode)

    result = subprocess.run([sys.executable, "cost_by_account.py"], check=False)
    if result.returncode != 0:
        print("Error: cost_by_account.py failed.", file=sys.stderr)
        sys.exit(result.returncode)

    logs_path = "logs.csv"
    run_finished_at = datetime.now(timezone.utc)
    with open(logs_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "run_started_at_utc",
                "run_finished_at_utc",
                "data_start_date",
                "data_end_date",
                "granularity",
                "group_by",
                "rows_written",
            ]
        )
        writer.writerow(
            [
                run_started_at.isoformat(),
                run_finished_at.isoformat(),
                start_date,
                end_date,
                args.granularity,
                args.group_by,
                total_rows,
            ]
        )

    if args.gcp_key and os.path.exists(args.gcp_key):
        _, sheet_url = upload_csv_to_google_sheet(
            logs_path,
            args.gcp_key,
            sheet_id=sheet_id,
            sheet_title=args.sheet_title,
            sheet_tab="logs",
            share_with=args.share_with,
        )
        print(f"Uploaded logs to Google Sheet: {sheet_url}")


if __name__ == "__main__":
    main()
