"""Admin Usuarios — view page entry point."""
from database.db import SessionLocal
from forms.admin_users_form import render_admin_users_panel

session = SessionLocal()
try:
    render_admin_users_panel(session)
finally:
    session.close()
