-- Seed: platform admin (L. Bandera).
-- Date: 2026-04-18
--
-- Rationale: the user explicitly requested naming lbandera@tradingsolutions.com
-- as a platform admin. The current role catalogue in services/users.py::VALID_ROLES
-- is ("comercial", "inside_sales", "compliance", "otro") -- there is no "admin"
-- role. Per user decision, lbandera is seeded with rol='compliance', which in
-- this platform is the equivalent of admin (same as the super-admin jsanchez).
--
-- Idempotent: re-running this script is a no-op if the row already exists
-- with the same values; otherwise updates the name/rol/activo fields.

INSERT INTO users (email, nombre_display, rol, activo, created_by)
VALUES ('lbandera@tradingsolutions.com', 'L. Bandera', 'compliance', TRUE, 'seed')
ON CONFLICT (email) DO UPDATE SET
    nombre_display = EXCLUDED.nombre_display,
    rol = EXCLUDED.rol,
    activo = EXCLUDED.activo;
