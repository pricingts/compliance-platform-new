# Architecture

## System Overview

The Compliance Platform is a Streamlit web application that manages compliance registration workflows for Trading Solutions. It connects to PostgreSQL for data persistence and integrates with Google Drive and Google Sheets for document storage and reporting.

```
                        ┌─────────────────────┐
                        │   Streamlit Cloud    │
                        │   (OAuth Provider)   │
                        └──────────┬──────────┘
                                   │ Authentication
                                   ▼
┌──────────┐           ┌─────────────────────┐           ┌──────────────────┐
│  Browser  │◄────────►│   Streamlit App      │◄────────►│   PostgreSQL 14  │
│  (User)   │   HTTP   │   (app.py)           │  SQLAlchemy│  (compliance_db) │
└──────────┘           │                      │           └──────────────────┘
                       │  ┌─────────────────┐ │
                       │  │ Services Layer  │ │           ┌──────────────────┐
                       │  │  - Auth         │ │──────────►│  Google Drive    │
                       │  │  - Drive Utils  │ │  API      │  (Documents)     │
                       │  │  - Sheets Writer│ │           └──────────────────┘
                       │  └─────────────────┘ │
                       │                      │           ┌──────────────────┐
                       │                      │──────────►│  Google Sheets   │
                       └─────────────────────┘  gspread   │  (Reporting)     │
                                                          └──────────────────┘
```

## Database Schema

The database contains 10 core tables plus an audit_log table. All tables use auto-incrementing integer primary keys.

### Table Relationships

```
profiles ─────────┐
   │               │
   │ 1:N           │ 1:N
   ▼               ▼
requests      document_type
   │               │
   ├── 1:N ────► registration ◄── comments (1:N)
   │
   ├── 1:N ────► customs_registration
   │
   ├── 1:N ────► port_registration
   │
   ├── 1:N ────► shipping_line_registration
   │
   └── 1:N ────► internal_registration

status (lookup) ──────► referenced by registration,
                        customs_registration,
                        port_registration,
                        shipping_line_registration,
                        internal_registration
```

### Tables

| Table | Purpose |
|---|---|
| `profiles` | Registration profile types (e.g., supplier, client) |
| `status` | Status lookup values (e.g., pending, approved, rejected) |
| `document_type` | Document categories per profile |
| `requests` | Compliance registration requests with company details |
| `comments` | Comments and notifications per request |
| `registration` | Document uploads linked to requests, with Drive links |
| `customs_registration` | Customs authority registrations |
| `port_registration` | Port and terminal registrations |
| `shipping_line_registration` | Shipping line registrations with routing details |
| `internal_registration` | Internal compliance registrations |
| `audit_log` | Tracks all data changes for compliance auditing |

### Key Columns in `requests`

The `requests` table is the central entity, tracking company name, commercial contact, trading entity, country, language, email, operation type, commodity, and flags for customs/port/shipping line requirements.

### Key Columns in `registration`

The `registration` table links uploaded documents to requests with file name, Google Drive link, upload timestamp, uploader identity, and status tracking.

## Authentication Flow

```
1. User visits the app
2. Streamlit checks st.user.is_logged_in
3. If not logged in --> show login button --> Streamlit Cloud OAuth
4. On successful OAuth --> st.session_state.authenticated = True
5. app.py reads st.user.email
6. identity_role() checks email against admin email list
7. Role determines visible pages:
   - "compliance" role: Home, Request Form, Document Upload, Progress
   - "other" role: Home, Request Form, Progress
```

### Admin Email Resolution

Admin emails are resolved in this order:
1. `ADMIN_EMAILS` environment variable (comma-separated list)
2. Fallback: Cross-product of `ADMIN_USERNAMES` x `ADMIN_DOMAINS`

## External Integrations

### Google Drive

- **Purpose**: Store uploaded compliance documents
- **Library**: `pydrive2`, `google-api-python-client`
- **Flow**: User uploads file via Streamlit -> app saves to Google Drive -> stores Drive link in `registration.drive_link`
- **Auth**: Service account credentials (JSON key file)

### Google Sheets

- **Purpose**: Sync compliance data for reporting and external visibility
- **Library**: `gspread`
- **Flow**: On request creation or status update -> sheets_writer syncs data to a shared Google Sheet
- **Auth**: Service account credentials (JSON key file)

## Data Flow

### Request Creation

```
User fills request form
    ├── Validates input (utils/validators.py)
    ├── Creates Request record in PostgreSQL
    ├── Creates related registrations based on profile:
    │   ├── registration (document slots)
    │   ├── customs_registration (if has_customs)
    │   ├── port_registration (if has_port)
    │   └── shipping_line_registration (if has_shipping_line)
    ├── Syncs to Google Sheets
    └── Logs action to audit_log
```

### Document Upload

```
Compliance user selects a request
    ├── Loads required document types for the request profile
    ├── User uploads file
    │   ├── File saved to Google Drive
    │   ├── Drive link stored in registration record
    │   └── Status updated
    └── Progress recalculated
```

### Progress Tracking

```
User opens Progress view
    ├── Queries requests (filtered by role)
    │   - Admin: sees all requests
    │   - Other: sees only own requests (by user_email)
    ├── For each request:
    │   ├── Counts total required documents
    │   ├── Counts completed documents (by status)
    │   └── Calculates completion percentage
    └── Displays summary with status indicators
```

## Layer Architecture

```
┌─────────────────────────────────────┐
│  Views (views/)                     │  Page-level Streamlit components
├─────────────────────────────────────┤
│  Forms (forms/)                     │  Reusable UI form components
├─────────────────────────────────────┤
│  Services (services/)               │  Business logic, external APIs
├─────────────────────────────────────┤
│  CRUD (database/crud/)              │  Database operations
├─────────────────────────────────────┤
│  Models (database/models/)          │  SQLAlchemy ORM definitions
├─────────────────────────────────────┤
│  Config (config/)                   │  Settings, environment resolution
├─────────────────────────────────────┤
│  Utils (utils/)                     │  Validators, error handling, timezone
└─────────────────────────────────────┘
```
