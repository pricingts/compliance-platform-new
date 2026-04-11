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
    has_shipping_line BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_email VARCHAR(255)
);

-- =====================
-- 5. Tabla comments
-- =====================
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    comments TEXT,
    notifications TEXT
);

-- =====================
-- 6. Tabla registration (documentos cargados)
-- =====================
CREATE TABLE registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    doc_type_id INTEGER REFERENCES document_type(id) ON DELETE CASCADE,
    id_comments INTEGER REFERENCES comments(id),
    status_id INTEGER REFERENCES status(id),
    file_name VARCHAR(255),
    drive_link TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by VARCHAR(150),
    razon_social VARCHAR(255),
    fecha_creacion date
);

-- =====================
-- 7. Tabla customs_registration (Aduanas)
-- =====================
CREATE TABLE customs_registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    customs_name VARCHAR(150) NOT NULL,
    status_id INTEGER REFERENCES status(id) ON DELETE SET NULL
);

-- =====================
-- 8. Tabla port_registration (Puertos y terminales)
-- =====================
CREATE TABLE port_registration (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    port_name VARCHAR(150) NOT NULL,
    terminal_name VARCHAR(150),
    status_id INTEGER REFERENCES status(id) ON DELETE SET NULL
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
    shipper_bl VARCHAR(255),
    status_id INTEGER REFERENCES status(id) ON DELETE SET NULL
);

CREATE TABLE internal_registration (
    id SERIAL PRIMARY KEY,
    request_id INT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    internal_label VARCHAR(255),
    status_id INT REFERENCES status(id)
);

-- =====================
-- 11. Tabla comment_entries (comentarios con atribucion)
-- =====================
CREATE TABLE comment_entries (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    author_email VARCHAR(255) NOT NULL,
    author_name VARCHAR(255),
    content TEXT NOT NULL,
    entry_type VARCHAR(50) DEFAULT 'comment',
    image_drive_link TEXT,
    image_file_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================
-- 12. Tabla notifications (notificaciones in-app)
-- =====================
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================
-- 13. Tabla audit_log
-- =====================
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_email VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id INTEGER,
    old_value TEXT,
    new_value TEXT,
    details TEXT
);

-- =====================
-- INDEXES
-- =====================
CREATE INDEX IF NOT EXISTS idx_requests_user_email ON requests(user_email);
CREATE INDEX IF NOT EXISTS idx_requests_company_name ON requests(company_name);
CREATE INDEX IF NOT EXISTS idx_requests_profile_id ON requests(profile_id);
CREATE INDEX IF NOT EXISTS idx_registration_request_id ON registration(request_id);
CREATE INDEX IF NOT EXISTS idx_customs_registration_request_id ON customs_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_port_registration_request_id ON port_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_shipping_line_registration_request_id ON shipping_line_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_internal_registration_request_id ON internal_registration(request_id);
CREATE INDEX IF NOT EXISTS idx_comment_entries_request_id ON comment_entries(request_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_email ON notifications(user_email);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity_id ON audit_log(entity_id);

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
