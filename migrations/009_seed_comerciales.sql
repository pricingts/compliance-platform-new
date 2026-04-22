-- Seed: active comerciales for the platform.
-- Date: 2026-04-21
--
-- Idempotent: re-running updates nombre_display / rol / activo to match
-- this canonical list. Safe to run on every deploy.
--
-- Rationale: the comercial catalogue lives in the `users` table (see
-- services/users.py::get_active_comerciales). Seeding them explicitly
-- ensures a fresh environment has the full sales roster available in the
-- "comercial" dropdown of the request form without manual admin steps.

INSERT INTO users (email, nombre_display, rol, activo, created_by)
VALUES
    ('sales@tradingsolutions.com',  'Pedro Luis Bruges', 'comercial', TRUE, 'seed_comerciales'),
    ('sales2@tradingsolutions.com', 'Sharon Zuñiga',     'comercial', TRUE, 'seed_comerciales'),
    ('sales3@tradingsolutions.com', 'Johnny Farah',      'comercial', TRUE, 'seed_comerciales'),
    ('sales4@tradingsolutions.com', 'Jorge Sánchez',     'comercial', TRUE, 'seed_comerciales'),
    ('sales5@tradingsolutions.com', 'Ivan Zuluaga',      'comercial', TRUE, 'seed_comerciales')
ON CONFLICT (email) DO UPDATE SET
    nombre_display = EXCLUDED.nombre_display,
    rol = EXCLUDED.rol,
    activo = EXCLUDED.activo;
