# AWS Cost Analyzer

This script pulls AWS Cost Explorer data from multiple AWS accounts and exports it to a CSV file. Optionally, it can upload the CSV to Google Sheets.

## Prerequisites

- Python 3.x
- AWS IAM credentials with Cost Explorer access
- (Optional) Google Cloud Service Account with Google Sheets API access

## Installation

1. Run the installation script:
```bash
./install.sh
```

## Quick Start

1. Copy and rename the example configuration files:
```bash
cp aws_accounts.json.example aws_accounts.json
cp key.json.example key.json
cp sheet_config.json.example sheet_config.json
```

2. Edit the configuration files with your actual credentials
3. Run the script:
```bash
python3 cost_analyzer.py
```

**Important:** The `.example` files are templates included in the repository. You must rename them and add your actual credentials before the script will work.

## Configuration

### 1. AWS Account Setup

#### Create AWS IAM User and Access Keys

For each AWS account you want to monitor:

1. Log into the AWS Console
2. Go to **IAM** > **Users** > **Add users**
3. Create a user (e.g., `cost-analyzer-reader`)
4. Select **Programmatic access**
5. Attach the following policies (or an equivalent least-privilege policy):
   - `AWSBillingReadOnlyAccess`
   - `IAMReadOnlyAccess` (for account alias)
6. Complete the user creation and **save the Access Key ID and Secret Access Key**

**Important:** Cost Explorer must be enabled for the account.

#### Configure aws_accounts.json

1. Copy the example configuration file:
```bash
cp aws_accounts.json.example aws_accounts.json
```

2. Edit `aws_accounts.json` and replace the example values with your actual AWS credentials:
```json
{
  "accounts": [
    {
      "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
      "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
      "region": "us-east-1"
    }
  ]
}
```

**Important:** Keep `aws_accounts.json` secure and never commit it to version control.

### 2. Google Cloud Service Account Setup (Optional)

If you want to upload results to Google Sheets:

1. Create or select a Google Cloud project
2. Enable the **Google Sheets API** and **Google Drive API**
3. Create a service account and download a JSON key
4. Copy the example file and replace it with your key:
```bash
cp key.json.example key.json
```

5. Store a target Google Sheet ID (optional):
```bash
cp sheet_config.json.example sheet_config.json
```
If you leave it blank, the script creates a new sheet for each run.
You can set `sheet_id` and `sheet_tab` to control where data is written.
If the file is missing or empty, the script logs a warning.

6. Use the service account email to share the target sheet or allow the script to create a new one

## Usage

### Run the script:
```bash
python3 cost_analyzer.py
```

This will:
1. Read AWS credentials from `aws_accounts.json`
2. Fetch Cost Explorer data for the last 30 days
3. Write results to `aws_costs.csv`
4. Upload the CSV to Google Sheets if `key.json` is present

### Summarize costs by service:
```bash
python3 cost_by_service.py
```

This will:
1. Read `aws_costs.csv`
2. Aggregate total cost per service
3. Write results to `cost_by_service.csv`
4. Upload the CSV to the `cost_by_service` tab in the same Google Sheet (if configured)

### Summarize costs by account:
```bash
python3 cost_by_account.py
```

This will:
1. Read `aws_costs.csv`
2. Aggregate total cost per account
3. Write results to `cost_by_account.csv`
4. Upload the CSV to the `cost_by_account` tab in the same Google Sheet (if configured)

### Command-line Options:

```bash
python3 cost_analyzer.py --help
```

Options:
- `--config`: Path to AWS accounts config file (default: `aws_accounts.json`)
- `--region`: Cost Explorer region (default: `us-east-1`)
- `--start-date`: Start date in YYYY-MM-DD (default: 30 days ago)
- `--end-date`: End date in YYYY-MM-DD (default: today, exclusive)
- `--granularity`: DAILY or MONTHLY (default: DAILY)
- `--group-by`: SERVICE or NONE (default: SERVICE)
- `--output`: Output CSV filename (default: `aws_costs.csv`)
- `--gcp-key`: Path to Google service account key (default: `key.json`)
- `--sheet-id`: Google Sheet ID to update (if omitted, a new sheet is created)
- `--sheet-config`: JSON file that stores the Google Sheet ID (default: `sheet_config.json`)
- `--sheet-tab`: Google Sheet tab name to write data into (default: `raw_data`)
- `--sheet-title`: Title for new Google Sheets (default: AWS Cost Analyzer)
- `--share-with`: Email to share the Google Sheet with

### cost_by_service.py Options:

```bash
python3 cost_by_service.py --help
```

Options:
- `--input`: Input CSV filename (default: `aws_costs.csv`)
- `--output`: Output CSV filename (default: `cost_by_service.csv`)
- `--gcp-key`: Path to Google service account key (default: `key.json`)
- `--sheet-config`: JSON file that stores the Google Sheet ID (default: `sheet_config.json`)
- `--sheet-tab`: Google Sheet tab name to write data into (default: `cost_by_service`)

### cost_by_account.py Options:

```bash
python3 cost_by_account.py --help
```

Options:
- `--input`: Input CSV filename (default: `aws_costs.csv`)
- `--output`: Output CSV filename (default: `cost_by_account.csv`)
- `--gcp-key`: Path to Google service account key (default: `key.json`)
- `--sheet-config`: JSON file that stores the Google Sheet ID (default: `sheet_config.json`)
- `--sheet-tab`: Google Sheet tab name to write data into (default: `cost_by_account`)

## Output

The script generates:
- **aws_costs.csv**: Local CSV file with cost data
- **Google Sheet**: Updated with the same data (if configured)

Columns:
- `account_id`: AWS Account ID
- `account_name`: AWS Account Alias
- `period_start`: Start date of the time period
- `period_end`: End date of the time period
- `granularity`: DAILY or MONTHLY
- `service`: AWS service name (empty if `--group-by NONE`)
- `amount`: Unblended cost amount
- `unit`: Currency (typically USD)

## Automation with Cron

To run the script automatically on a schedule:

1. Open crontab:
```bash
crontab -e
```

2. Add a line to run the script (example: every day at 2 AM):
```
0 2 * * * cd /home/ubuntu/aws-cost-analyzer && python3 cost_analyzer.py >> /home/ubuntu/aws-cost-analyzer/aws_costs.log 2>&1
```

3. Check the log file for output:
```bash
tail -f /home/ubuntu/aws-cost-analyzer/aws_costs.log
```

## Security Best Practices

1. **Protect your credentials:**
   - Never commit `aws_accounts.json` or `key.json` to version control
   - Set appropriate file permissions: `chmod 600 aws_accounts.json key.json sheet_config.json`

2. **Use least privilege:**
   - AWS IAM users should have read-only billing access
   - Google Service Account should only have access to the target sheet

3. **Rotate credentials regularly:**
   - Update AWS access keys periodically
   - Regenerate Google service account keys as needed

## Troubleshooting

### "AccessDeniedException" for Cost Explorer
Make sure Cost Explorer is enabled and the IAM user has `ce:GetCostAndUsage` permission.

### "No module named 'boto3'" error
Install dependencies:
```bash
pip3 install --break-system-packages boto3
```

### "Google Sheets upload skipped"
Provide `key.json` or pass `--gcp-key` with the path to your key file.
