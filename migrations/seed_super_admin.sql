-- Seed: single super-admin row.
-- Date: 2026-04-14
--
-- Policy: only one user is hardcoded in the database. Every other user
-- (comerciales, inside sales, other compliance members) is created from the
-- admin panel in the UI. This means adding/removing users never requires
-- a redeploy.
--
-- If this email ever changes, update this file AND the super-admin guard
-- in forms/admin_users_form.py (which prevents disabling the super-admin).

INSERT INTO users (email, nombre_display, rol, activo, created_by)
VALUES ('jsanchez@tradingsolutions.com', 'Juan Sanchez', 'compliance', TRUE, 'seed')
ON CONFLICT (email) DO UPDATE SET
    nombre_display = EXCLUDED.nombre_display,
    rol = EXCLUDED.rol,
    activo = EXCLUDED.activo;
