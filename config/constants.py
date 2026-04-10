"""Centralized constants for the compliance platform.

All magic strings and hardcoded values extracted from form files.
Single source of truth for UI options and business data.
"""

# Commercial contacts
COMERCIALES = [
    "Pedro Luis Bruges",
    "Andres Consuegra",
    "Ivan Zuluaga",
    "Sharon Zuniga",
    "Johnny Farah",
    "Felipe Hoyos",
    "Jorge Sanchez",
    "Irina Paternina",
    "Stephanie Bruges",
]

# Port/terminal mappings (complete)
TERMINALES = {
    "Buenaventura": ["TCBUEN", "AGUA DULCE", "SPRBUN"],
    "Cartagena": ["COMPAS", "CONTECAR/SPRC"],
}

# Trading entity countries
TRADING_COUNTRIES = [
    "Colombia",
    "Mexico",
    "Panama",
    "Estados Unidos",
    "Chile",
    "Ecuador",
    "Peru",
    "Hong Kong",
]

# Reminder frequency options
REMINDER_FREQUENCIES = [
    "Una vez por semana",
    "Dos veces por semana",
    "Tres veces por semana",
]

# Operation types
OPERATION_TYPES = ["EXPO", "IMPO"]

# Customs systems
CUSTOMS_SYSTEMS = [
    "CARGOFLASH",
    "SIAP",
    "MOVIADUANA",
    "ITBF - USA",
    "GOMSA - MEX",
]

# Shipping line names
SHIPPING_LINES = ["MSC", "ONE", "Otro"]

# Internal document type labels (for upload form)
INTERNAL_DOC_LABELS = ["empresa", "vinculacion", "seguridad"]

# Document type ID mappings by profile ID
# Maps profile_id -> {label -> doc_type_id}
DOC_TYPE_MAPPINGS = {
    1: {"empresa": 1, "vinculacion": 2, "seguridad": 3},
    2: {"empresa": 4, "vinculacion": 5, "seguridad": 6},
}

# Maximum file size for uploads (bytes) -- 10 MB
MAX_UPLOAD_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_FILE_SIZE_MB = 10

# Default pagination
DEFAULT_PAGE_SIZE = 20
