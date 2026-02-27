"""
Example configuration for local development.
Copy to `src/config_local.py` (add to .gitignore) and set real secrets there or use environment variables.
This file should NOT be committed with real credentials.
"""
import os
from pathlib import Path

# Optional: load .env file for local dev (install python-dotenv)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    # dotenv is optional; environment variables can be set via your shell/CI
    pass

# Primary connection string (preferred). Provide a full ODBC-style connection string.
CONNECTION_STRING = os.getenv('CONNECTION_STRING') or ''

# If you prefer to build from parts, you can set these instead
DB_SERVER = os.getenv('DB_SERVER')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Sample fallback to build a connection string only if all parts are provided
if not CONNECTION_STRING and DB_SERVER and DB_NAME and DB_USER and DB_PASSWORD:
    CONNECTION_STRING = (
        f"Driver={'{ODBC Driver 18 for SQL Server}'};"
        f"Server={DB_SERVER};Database={DB_NAME};"
        f"Uid={DB_USER};Pwd={DB_PASSWORD};Encrypt=yes;"
        "TrustServerCertificate=no;Connection Timeout=30;"
    )

# Export other config values here as needed (copy them from your original config.py)
# e.g. HOURLY_MULTIPLIERS = [...], etc.
