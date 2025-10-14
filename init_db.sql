-- =========================================================
-- MODELO DE DATOS COMPLIANCE
-- Versión extendida con registros de Aduana, Puerto y Línea Naviera
-- =========================================================

-- =====================
-- 1. Tabla profiles
-- =====================
CREATE TABLE profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

-- =====================
-- 2. Tabla status
-- =====================
CREATE TABLE status (
    id SERIAL PRIMARY KEY,
    status VARCHAR(100) NOT NULL
);

-- =====================
-- 3. Tabla document_type
-- =====================
CREATE TABLE document_type (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    category VARCHAR(150) NOT NULL
);

-- =====================
-- 4. Tabla requests
-- =====================
CREATE TABLE requests (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    commercial VARCHAR(255),
    company_name VARCHAR(255),
    trading VARCHAR(100),
    country VARCHAR(100),
    language VARCHAR(50),
    email VARCHAR(255),
    reminder_frequency VARCHAR(100),
    operation_type VARCHAR(50),
    commodity VARCHAR(255),
    customs_req TEXT,
    has_customs BOOLEAN DEFAULT FALSE,
    has_port BOOLEAN DEFAULT FALSE,
    has_shipping_line BOOLEAN DEFAULT FALSE
);

-- =====================
-- 5. Tabla registration (documentos cargados)
-- =====================
CREATE TABLE registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    doc_type_id INTEGER NOT NULL REFERENCES document_type(id) ON DELETE CASCADE,
    id_comments INTEGER REFERENCES comments(id),
    status_id INTEGER REFERENCES status(id),
    file_name VARCHAR(255),
    drive_link TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by VARCHAR(150),
    razon_social VARCHAR(255)
);

-- =====================
-- 6. Tabla comments
-- =====================
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    comments TEXT,
    notifications TEXT
);

-- =====================
-- 7. Tabla customs_registration (Aduanas)
-- =====================
CREATE TABLE customs_registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    customs_name VARCHAR(150) NOT NULL
);

-- =====================
-- 8. Tabla port_registration (Puertos y terminales)
-- =====================
CREATE TABLE port_registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    port_name VARCHAR(150) NOT NULL,
    terminal_name VARCHAR(150)
);

-- =====================
-- 9. Tabla shipping_line_registration (Líneas navieras)
-- =====================
CREATE TABLE shipping_line_registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    line_name VARCHAR(150) NOT NULL,
    pol VARCHAR(150),
    pod VARCHAR(150),
    product VARCHAR(255),
    container_type VARCHAR(50),
    shipper_bl VARCHAR(255)
);

CREATE TABLE internal_registration (
    id SERIAL PRIMARY KEY,
    request_id INT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    internal_label VARCHAR(255),
    status_id INT REFERENCES status(id)
);

-- =========================================================
-- 🔗 Relaciones y Consideraciones
-- =========================================================
-- profiles        1 ───< document_type
-- profiles        1 ───< requests
-- status          1 ───< document_type
-- requests        1 ───< registration
-- requests        1 ───< comments
-- requests        1 ───< customs_registration
-- requests        1 ───< port_registration
-- requests        1 ───< shipping_line_registration
-- document_type   1 ───< registration
-- comments        1 ───< registration (opcional, id_comments)
