# Development Guide

## Local Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for PostgreSQL)
- Git

### 1. Clone and Install

```bash
git clone <repo-url>
cd compliance-platform-new

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with your local values:

```
DATABASE_URL=postgresql://admin:admin@localhost:5433/compliance_new_db
ENV=dev
LOG_LEVEL=DEBUG
```

## Database Setup

### Option A: Docker Compose (Recommended)

```bash
# Start PostgreSQL only
docker-compose up db -d

# The init_db.sql script runs automatically on first startup
# Database is available at localhost:5433
```

### Option B: Standalone PostgreSQL

```bash
# Create the database
createdb compliance_new_db

# Run the schema
psql compliance_new_db < init_db.sql

# Update .env with your connection string
# DATABASE_URL=postgresql://user:password@localhost:5432/compliance_new_db
```

### Verify Database Connection

```bash
psql postgresql://admin:admin@localhost:5433/compliance_new_db -c "\dt"
```

You should see all 10 tables listed.

## Running the App Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Start the Streamlit app
streamlit run app.py
```

The app will be available at `http://localhost:8501`.

Note: Authentication features require Streamlit Cloud OAuth configuration. For local development, you may need to mock the authentication layer or configure Streamlit secrets.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/unit -v

# Run a specific test file
pytest tests/unit/test_models.py -v

# Run tests matching a keyword
pytest tests/ -k "test_request" -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Run with short traceback (useful in CI)
pytest tests/unit -v --tb=short

# Stop on first failure
pytest tests/ -x
```

### Test Markers

Tests are organized with pytest markers defined in `pyproject.toml`:

```bash
# Run only unit tests by marker
pytest -m unit

# Run only integration tests by marker
pytest -m integration
```

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures (mock sessions, factories)
├── unit/
│   ├── test_models.py           # ORM model tests
│   ├── test_clientes_crud.py    # Client CRUD operations
│   ├── test_upsert_status.py    # Status upsert logic
│   ├── test_auth_roles.py       # Authentication and role tests
│   ├── test_validators.py       # Input validation tests
│   ├── test_sheets_writer.py    # Google Sheets sync tests
│   ├── test_google_drive_utils.py # Drive integration tests
│   ├── test_error_handling.py   # Error handler tests
│   ├── test_timezone.py         # Timezone utility tests
│   ├── test_view_progress.py    # Progress view tests
│   ├── test_audit.py            # Audit logging tests
│   ├── test_healthcheck.py      # Health check endpoint tests
│   └── test_placeholder.py      # Placeholder/scaffold tests
└── integration/
    └── (integration tests)
```

## Code Style

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, configured in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 120
target-version = "py311"
```

### Running the Linter

```bash
# Check for issues
ruff check .

# Auto-fix what can be fixed
ruff check --fix .

# Format code
ruff format .
```

### Type Checking

```bash
mypy .
```

Configured in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
```

## Pre-commit Hooks

The project includes pre-commit hooks that run Ruff and unit tests before each commit:

```bash
# Install pre-commit
pip install pre-commit

# Set up hooks
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files
```

Hooks configured in `.pre-commit-config.yaml`:
- **ruff**: Lint with auto-fix
- **ruff-format**: Code formatting
- **pytest-unit**: Runs unit tests (fails commit if tests fail)

## TDD Methodology

This project follows Test-Driven Development:

1. **Write a failing test** for the new feature or bug fix
2. **Implement the minimum code** to make the test pass
3. **Refactor** while keeping tests green
4. **Repeat** for the next requirement

Test files follow the naming convention `test_<module>.py` and are placed in `tests/unit/` or `tests/integration/` depending on their dependencies.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready code. Deploys to Railway. |
| `dev` | Integration branch for development work. |
| `feature/*` | Feature branches, created from `dev`. |
| `fix/*` | Bug fix branches, created from `main` or `dev`. |

### Workflow

1. Create a feature branch from `dev`: `git checkout -b feature/my-feature dev`
2. Develop and commit with passing tests
3. Push and open a PR to `dev`
4. CI runs lint, tests, and Docker build
5. After review and merge to `dev`, create a PR from `dev` to `main` for release
