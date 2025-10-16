from forms.view_progress import show_progress_view

def show(current_user_email: str | None = None, is_admin: bool = False):
    show_progress_view(current_user_email, is_admin)
