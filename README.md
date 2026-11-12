# MajiCare

MajiCare is a Flask application for tracking community water points and resident water-service reports.

## Features

- Resident registration and sign-in
- Administrator account management from the protected admin dashboard
- Community and water-point directories
- Water-point map and status tracking
- Resident reports and administrator status management
- Administrator responses to reports, visible in the resident's report history
- JSON API endpoints
- Responsive signed-in dashboard with live water-point and report summaries
- Optional verified map coordinates for administrator-added water points
- In-app resident messages reviewed from the administrator dashboard

## Requirements

- Python 3.10 or newer
- pip

## Run locally

From the project root, create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Set a stable secret for your local session and start the app:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

Open <http://127.0.0.1:5000>. The SQLite database is created at `instance/majicare.db` when the app initializes.

For deployment, configure `SECRET_KEY` as an environment variable and keep it stable between restarts. Do not commit real secrets.

Public registration creates Resident accounts. Administrators can create additional admin accounts from the protected admin dashboard. To create the first administrator on a new installation, run this command from the project root:

```powershell
flask --app app:create_app create-admin <username>
```

The command prompts for a password and is available only through the trusted local command line. Existing administrators can create further admin accounts in the dashboard without an invite code.

The signed-in dashboard is available at <http://127.0.0.1:5000/dashboard>. Administrators can open a report from the admin page, post a response, and see the response history. Residents can view responses from **My Reports**. Water-point map markers use saved coordinates only; points without verified coordinates stay in the directory and are not plotted. Administrators can enter optional latitude and longitude values when adding a water point. Residents can use **Contact Admin** on the dashboard; messages appear in the administrator dashboard.

## Tests

```powershell
python -m pytest -q
```
