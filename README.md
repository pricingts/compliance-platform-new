# Compliance Platform

A compliance management platform for Trading Solutions. Tracks supplier and client registration requests, manages document uploads to Google Drive, and provides real-time progress visibility for the compliance team.

## Tech Stack

- **Frontend**: Streamlit 1.44
- **Database**: PostgreSQL 14, SQLAlchemy 2.0, Alembic migrations
- **Authentication**: Streamlit Cloud OAuth with role-based access
- **External APIs**: Google Drive API, Google Sheets API (gspread)
- **PDF Generation**: ReportLab
- **Infrastructure**: Docker, Railway

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 14 (or use the Docker Compose setup)

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd compliance-platform-new

# 2. Copy environment file and fill in your values
cp .env.example .env

# 3. Start with Docker Compose
docker-compose up --build

# 4. Access the application
open http://localhost:8501
```

## Development Setup

```bash
# Create and activate a virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Start the database (if not running standalone PostgreSQL)
docker-compose up db -d

# Run the application locally
streamlit run app.py

# Run tests
pytest tests/ -v

# Run linting
ruff check .

# Run type checking
mypy .
```

## Project Structure

```
compliance-platform-new/
├── app.py                   # Streamlit entry point and routing
├── config/
│   └── settings.py          # Admin emails, environment config
├── database/
│   ├── db.py                # SQLAlchemy engine and session setup
│   ├── models/
│   │   ├── base.py          # Declarative base
│   │   └── models.py        # ORM models (10 tables)
│   └── crud/
│       ├── clientes.py      # Client/supplier CRUD operations
│       └── documents.py     # Document registration CRUD
├── forms/
│   ├── request_form.py      # New request creation form
│   ├── upload_documents_form.py  # Document upload form
│   └── view_progress.py     # Progress tracking view
├── services/
│   ├── authentication.py    # Streamlit OAuth authentication
│   ├── google_drive_utils.py # Google Drive file operations
│   ├── sheets_writer.py     # Google Sheets sync
│   └── logging_config.py    # Structured logging setup
├── utils/
│   ├── error_handlers.py    # Error handling decorators
│   ├── exceptions.py        # Custom exception classes
│   ├── timezone.py          # Timezone utilities
│   └── validators.py        # Input validation helpers
├── views/
│   ├── request.py           # Request page view
│   ├── upload_documents.py  # Upload page view
│   └── progress.py          # Progress page view
├── tests/
│   ├── conftest.py          # Shared fixtures
│   ├── unit/                # Unit tests (114 tests)
│   └── integration/         # Integration tests
├── docs/                    # Project documentation
├── Dockerfile               # Production container image
├── docker-compose.yml       # Local development stack
├── railway.toml             # Railway deployment config
├── Procfile                 # Process definition for PaaS
├── init_db.sql              # Database schema DDL
├── pyproject.toml           # Project metadata, tool config
├── requirements.txt         # Production dependencies
└── requirements-dev.txt     # Development dependencies
```

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `ENV` | Environment name (`dev`, `staging`, `production`) | No (default: `dev`) |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) | No (default: `INFO`) |
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | Path to Google Drive service account JSON | For Drive features |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | Path to Google Sheets service account JSON | For Sheets sync |
| `ADMIN_EMAILS` | Comma-separated admin email addresses | No (built from usernames/domains) |
| `ADMIN_USERNAMES` | Comma-separated admin usernames | No (has defaults) |
| `ADMIN_DOMAINS` | Comma-separated email domains for admins | No (has defaults) |

## Deployment

The platform deploys to Railway using the configuration in `railway.toml`. See [docs/deployment.md](docs/deployment.md) for detailed deployment instructions.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests
pytest tests/unit -v

# Run only integration tests
pytest tests/integration -v

# Run tests with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Run tests matching a keyword
pytest tests/ -k "test_request" -v
```

### Test Markers

- `@pytest.mark.unit` -- Unit tests (fast, no external dependencies)
- `@pytest.mark.integration` -- Integration tests (require database/services)

## CI/CD

GitHub Actions runs on every push to `main`/`dev` and on pull requests to `main`:

- **Lint**: Checks code style with `ruff`
- **Test**: Runs unit tests against a PostgreSQL 14 service container
- **Docker Build**: Validates the Docker image builds successfully

## License

Proprietary -- Trading Solutions
