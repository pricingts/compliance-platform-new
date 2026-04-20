# Release Checklist — Mailer migration & error-handling hardening

This release ships:

- A Python-native compliance-notification mailer (replaces the Google Apps
  Script trigger on the "Solicitudes de Creacion" sheet).
- Case ID (`C0042` format) visible in the email subject, body, and the
  first column of the Google Sheet.
- `lbandera@tradingsolutions.com` seeded as a platform admin with the
  `compliance` role.
- Retries + timeouts on Drive/Sheets, narrowed exception handling across
  forms/views/services, and sanitized user-facing error messages.
- New utilities: `transactional_session`, `@with_retry`, `@log_errors`,
  `sanitize_for_user`, `MailerError`, `SheetsError`.

Feature branch: `feat/mailer-migration-and-error-hardening`
Commits ahead of main: 8.
Total tests on branch: **392** (vs. 309 baseline — +83 new).

---

## Pre-flight (local, before pushing anything)

- [x] Full suite passes locally: `python3 -m pytest tests/unit tests/integration -q` → 392 ok.
- [x] Ruff clean: `ruff check .`.
- [x] Branches merged into main deleted locally.
- [x] Feature branch has no leftover debug code, TODOs, or private paths.
- [x] `.env.example` updated with new `MAILER_ENABLED` / `SMTP_*` keys.
- [x] `migrations/run_migration.py` is generic (accepts .sql files as args).
- [x] Scripts executable: `scripts/setup_local_testing.sh`, `scripts/apply_migrations_railway.sh`.

## Phase A — Testing in development (what YOU have to do)

These steps exercise the whole stack against real Postgres and real Google
Sheets, so Claude can't do them for you. Budget: ~20 minutes.

### A.1 Local Docker testing

1. Make sure Docker Desktop is running.
2. From the project root, run:
   ```bash
   ./scripts/setup_local_testing.sh
   ```
   This brings Postgres up on :5433, applies migrations 005/006, installs
   deps, seeds super-admin + lbandera, and runs the pytest suite against
   the real Postgres. All 392 tests should pass.

### A.2 Gmail App Password

The mailer uses SMTP with the corporate Gmail account
`compliance@tradingsolutions.com`. Create an App Password:

1. Sign in as `compliance@tradingsolutions.com`.
2. Go to <https://myaccount.google.com/apppasswords> (requires 2FA).
3. Create a password named "Compliance Platform Mailer".
4. Copy the 16-character password.

### A.3 Railway dev environment — apply migrations

⚠️ Claude could not do this directly because the local Railway CLI token
was expired when this branch was built. You need to run:

```bash
railway login           # re-auth if needed
railway link            # if not already linked
./scripts/apply_migrations_railway.sh dev
```

The script prints the final state of the `users` table; confirm
`lbandera@tradingsolutions.com` appears with `rol='compliance'`.

### A.4 Railway dev environment — set new secrets

```bash
railway environment dev

railway variables --set "MAILER_ENABLED=true"
railway variables --set "SMTP_HOST=smtp.gmail.com"
railway variables --set "SMTP_PORT=465"
railway variables --set "SMTP_USE_TLS=false"
railway variables --set "SMTP_USERNAME=compliance@tradingsolutions.com"
railway variables --set "SMTP_PASSWORD=<the 16-char App Password>"
railway variables --set "SMTP_FROM_ADDR=compliance@tradingsolutions.com"
```

Do NOT set `MAILER_ENABLED=true` in production yet. Only in dev.

### A.5 Push the branch to activate CI + deploy to dev

```bash
git push -u origin feat/mailer-migration-and-error-hardening
```

CI (GitHub Actions) will run lint + test + docker-build. Verify green.

To deploy the dev Railway service from this branch, either:

- Configure the dev Railway service to track
  `feat/mailer-migration-and-error-hardening`, or
- Push the same commits to a `dev` branch (if the dev service tracks it).

### A.6 Smoke tests on dev (Railway dev URL)

Sign in with a test `comercial` user and create one new request
("TEST-VERIFY-A"). Verify, in order:

- [ ] In Google Sheet "Solicitudes de Creacion": new row, first column is the
      Case ID (`C00XX`).
- [ ] Gmail inbox of `compliance@`, `compliance1@`, `compliance2@`, AND
      `lbandera@`: email arrives with subject
      `"Solicitud de Registro - C00XX - TEST-VERIFY-A"`.
- [ ] Email body shows the Case ID banner + full field table.
- [ ] Comercial's inbox (CC): the same email.
- [ ] DB: `SELECT case_id, email_notified_at FROM requests WHERE company_name='TEST-VERIFY-A'`
      returns one row with `email_notified_at NOT NULL`.
- [ ] Apps Script coexistence: the legacy script may also have fired for this
      row (two emails possible during overlap). The new Python email is the
      one with the Case ID in the subject — easy to distinguish.

### A.7 Invite a colleague to apply as compliance dynamically

Log in to the dev Streamlit as an admin (jsanchez or lbandera) → Usuarios →
create `testcompliance@tradingsolutions.com` with rol `compliance`. Create a
new request and confirm the new email is in TO automatically (the resolver
queries `users` on every send).

### A.8 SMTP failure simulation

Temporarily break `SMTP_PASSWORD` in Railway dev, create a request, confirm:

- [ ] Request is saved in DB.
- [ ] Sheet row is written.
- [ ] User sees a sanitized warning ("No se pudo enviar la notificación…"),
      no stack trace, no password leaking.
- [ ] `email_notified_at` stays NULL so a retry re-attempts later.
- [ ] Fix the password; the next request succeeds.

---

## Phase B — Prod rollout (only after Phase A is GREEN)

### B.1 Merge to main

1. Open PR `feat/mailer-migration-and-error-hardening` → `main`.
2. Request review if applicable; or self-merge after CI is green.
3. Railway prod typically redeploys automatically on merge.

### B.2 Apply migrations to prod

```bash
railway environment production
./scripts/apply_migrations_railway.sh production
```

Both migrations are idempotent — safe to re-run.

### B.3 Seed prod secrets

Same keys as Phase A.4, but in the prod environment. Keep
`MAILER_ENABLED=false` initially.

```bash
railway environment production
railway variables --set "MAILER_ENABLED=false"
railway variables --set "SMTP_HOST=smtp.gmail.com"
railway variables --set "SMTP_PORT=465"
railway variables --set "SMTP_USE_TLS=false"
railway variables --set "SMTP_USERNAME=compliance@tradingsolutions.com"
railway variables --set "SMTP_PASSWORD=<16-char App Password>"
railway variables --set "SMTP_FROM_ADDR=compliance@tradingsolutions.com"
```

### B.4 Flip MAILER_ENABLED in prod

Once the dev soak lasted at least 48 h with zero SMTP incidents, flip the
flag:

```bash
railway environment production
railway variables --set "MAILER_ENABLED=true"
```

Railway should trigger a redeploy automatically.

### B.5 Observe production

Create one low-stakes test request in prod (or wait for the first organic
one). Verify in the 4 recipients' inboxes that:

- The Python email with Case ID in subject arrives.
- The legacy Apps Script email also arrives (expected during overlap).

### B.6 Disable the Apps Script trigger

After 7 days of overlap with zero incidents:

1. Open the Google Sheet "Solicitudes de Creacion".
2. Extensions → Apps Script.
3. Triggers → disable or delete the `enviarCorreosPendientes` scheduled
   trigger. Leave the function in place for 30 days as safety net.
4. After 30 days with Python-only delivery, delete the Apps Script code.

### B.7 Remove the coexistence commentary in the code

Delete or shorten the comment block in `forms/request_form.py` near the
`send_request_notification(...)` call that warns about the Apps Script
overlap. Ship a trivial follow-up PR.

---

## Rollback

If any issue appears in prod:

```bash
railway environment production
railway variables --set "MAILER_ENABLED=false"
```

Takes seconds; the Apps Script keeps emails flowing. No data loss because
the mailer is best-effort and `email_notified_at` is only set on success.

If a migration caused issues (extremely unlikely — both are additive):

- 005: `ALTER TABLE requests DROP COLUMN email_notified_at;`
- 006: `DELETE FROM users WHERE email='lbandera@tradingsolutions.com' AND created_by='seed';`

Only do this if you are sure the column / row is truly the cause.

---

## Known follow-ups (filed for future work)

- **Drive transport timeout**: currently relies on `resumable=True` + retry
  decorator; switching to `AuthorizedHttp(timeout=30)` is TODO (phase 6).
- **CRUDs retrofit to `transactional_session`**: deferred to keep this
  release small. Tracking under "Fase 4b future".
- **`forms/my_requests_view.py:63` latent bug**: fixed in commit `fade678`.
