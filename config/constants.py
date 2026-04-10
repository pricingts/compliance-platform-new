"""Centralized constants for the compliance platform.

All magic strings and hardcoded values extracted from form files.
Single source of truth for UI options and business data.
"""

# Commercial contacts
COMERCIALES = [
    "Pedro Luis Bruges",
    "Andrés Consuegra",
    "Ivan Zuluaga",
    "Sharon Zuñiga",
    "Johnny Farah",
    "Felipe Hoyos",
    "Jorge Sánchez",
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

# Port names for multiselect
PORTS = ["Cartagena", "Barranquilla", "Santa Marta", "Buenaventura"]

# MSC container types
MSC_CONTAINER_TYPES = ["20' DRY", "40' DRY", "40' HC", "OTRO"]

# Language options
LANGUAGES = ["Español", "Inglés"]

# Provider types
PROVIDER_TYPES = ["Logístico", "No Logístico"]

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
