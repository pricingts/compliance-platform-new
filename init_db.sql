CREATE TABLE profiles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL -- e.g., 'cliente', 'proveedor', etc.
);

INSERT INTO profiles (name) VALUES
  ('cliente'),
  ('proveedor')

CREATE TABLE document_type (
  id SERIAL PRIMARY KEY,
  profile_id INTEGER NOT NULL REFERENCES profiles(id),
  
)