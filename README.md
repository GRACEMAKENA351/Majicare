# MajiCare

MajiCare is a Flask application for tracking community water points and resident water-service reports.

## Features

- Resident registration and sign-in
- Community and water-point directories
- Water-point map and status tracking
- Resident reports and administrator status management
- JSON API endpoints

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

## Tests

```powershell
python -m pytest -q
```
