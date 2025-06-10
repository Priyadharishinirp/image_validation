from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    """
    Decorator that checks if the current user is authenticated and has admin role.
    If not, redirects to the login page or dashboard with a message.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if the user is logged in
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))

        # Check if the user is an admin
        if current_user.role != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)

    return decorated_function
