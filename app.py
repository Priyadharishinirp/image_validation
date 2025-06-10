# app.py - Main Flask application
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import datetime
from image_compare import compare_images, create_gif_from_images
from decorators import admin_required
#from image_compare import compare_images, create_optimized_gif
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///image_comparison.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['OUTPUT_FOLDER'] = 'static/outputs/'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit

# Create folders if they don't exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# Initialize database
db = SQLAlchemy(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(20), default='user')  # Options: 'admin', 'user'
    comparisons = db.relationship('Comparison', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Comparison(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    image1_path = db.Column(db.String(255))
    image2_path = db.Column(db.String(255))
    gif_path = db.Column(db.String(255))
    color_diff1_path = db.Column(db.String(255))
    color_diff2_path = db.Column(db.String(255))
    gray_diff1_path = db.Column(db.String(255))
    gray_diff2_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_public = db.Column(db.Boolean, default=False)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    public_comparisons = Comparison.query.filter_by(is_public=True).order_by(Comparison.created_at.desc()).limit(5).all()
    return render_template('index.html', public_comparisons=public_comparisons)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user_exists = User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first()
        if user_exists:
            flash('Username or email already exists')
            return redirect(url_for('register'))

        # Create the first user as admin, others as regular users
        role = 'admin' if User.query.count() == 0 else 'user'

        new_user = User(username=username, email=email, role=role)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))

        flash('Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_comparisons = Comparison.query.filter_by(user_id=current_user.id).order_by(Comparison.created_at.desc()).all()
    return render_template('dashboard.html', comparisons=user_comparisons)

@app.route('/team')
@login_required
def team():
    if current_user.role != 'admin':
        flash('You do not have permission to view the team page')
        return redirect(url_for('dashboard'))

    users = User.query.all()
    return render_template('team.html', users=users)

@app.route('/admin/promote/<int:user_id>')
@login_required
def promote_user(user_id):
    if current_user.role != 'admin':
        flash('You do not have permission to promote users')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    user.role = 'admin'
    db.session.commit()

    flash(f'User {user.username} promoted to admin')
    return redirect(url_for('team'))

@app.route('/admin/demote/<int:user_id>')
@login_required
def demote_user(user_id):
    if current_user.role != 'admin':
        flash('You do not have permission to demote users')
        return redirect(url_for('dashboard'))

    # Prevent self-demotion to ensure there's always at least one admin
    if user_id == current_user.id:
        flash('Cannot demote yourself')
        return redirect(url_for('team'))

    user = User.query.get_or_404(user_id)
    user.role = 'user'
    db.session.commit()

    flash(f'User {user.username} demoted to user')
    return redirect(url_for('team'))

@app.route('/compare', methods=['GET', 'POST'])
@login_required
def compare():
    if request.method == 'POST':
        image1 = request.files.get('image1')
        image2 = request.files.get('image2')
        title = request.form.get('title', 'Untitled Comparison')
        description = request.form.get('description', '')
        is_public = 'is_public' in request.form

        if not image1 or not image2:
            flash('Both images are required')
            return redirect(url_for('compare'))

        uid = uuid.uuid4().hex

        # Save uploaded images
        path1 = os.path.join(app.config['UPLOAD_FOLDER'], f"{uid}_img1.png")
        path2 = os.path.join(app.config['UPLOAD_FOLDER'], f"{uid}_img2.png")
        image1.save(path1)
        image2.save(path2)

        # Define output paths
        out1 = os.path.join(app.config['OUTPUT_FOLDER'], f"{uid}_out1.jpg")
        out2 = os.path.join(app.config['OUTPUT_FOLDER'], f"{uid}_out2.jpg")
        gif_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uid}_output.gif")

        # Process images
        compare_results = compare_images(path1, path2, out1, out2, mode="both")
        create_gif_from_images(path1, path2, gif_path)

        # Create database entry
        comparison = Comparison(
            user_id=current_user.id,
            title=title,
            description=description,
            image1_path=path1,
            image2_path=path2,
            gif_path=gif_path,
            color_diff1_path=compare_results.get('color1'),
            color_diff2_path=compare_results.get('color2'),
            gray_diff1_path=compare_results.get('gray1'),
            gray_diff2_path=compare_results.get('gray2'),
            is_public=is_public
        )

        db.session.add(comparison)
        db.session.commit()

        return redirect(url_for('view_comparison', comparison_id=comparison.id))

    return render_template('compare.html')
from pathlib import Path

@app.route('/comparison/<int:comparison_id>')
def view_comparison(comparison_id):
    comparison = Comparison.query.get_or_404(comparison_id)

    if not comparison.is_public and (not current_user.is_authenticated or current_user.id != comparison.user_id):
        flash('You do not have permission to view this comparison')
        return redirect(url_for('index'))

    # Normalize paths for use in HTML
    def relative_static_path(full_path):
        if full_path and 'static/' in full_path:
            return str(Path(full_path).relative_to('static'))
        return None

    comparison.gif_path = relative_static_path(comparison.gif_path)
    comparison.color_diff1_path = relative_static_path(comparison.color_diff1_path)
    comparison.color_diff2_path = relative_static_path(comparison.color_diff2_path)
    comparison.gray_diff1_path = relative_static_path(comparison.gray_diff1_path)
    comparison.gray_diff2_path = relative_static_path(comparison.gray_diff2_path)
    comparison.image1_path = relative_static_path(comparison.image1_path)
    comparison.image2_path = relative_static_path(comparison.image2_path)

    file_paths = {
        'color_diff1_exists': bool(comparison.color_diff1_path),
        'color_diff2_exists': bool(comparison.color_diff2_path),
        'gray_diff1_exists': bool(comparison.gray_diff1_path),
        'gray_diff2_exists': bool(comparison.gray_diff2_path),
        'gif_exists': bool(comparison.gif_path),
        'image1_exists': bool(comparison.image1_path),
        'image2_exists': bool(comparison.image2_path)
    }

    return render_template('comparison.html', comparison=comparison, file_paths=file_paths)


@app.route('/delete/<int:comparison_id>')
@login_required
def delete_comparison(comparison_id):
    comparison = Comparison.query.get_or_404(comparison_id)

    # Ensure the user owns this comparison or is an admin
    if current_user.id != comparison.user_id and current_user.role != 'admin':
        flash('You do not have permission to delete this comparison')
        return redirect(url_for('dashboard'))

    # Delete associated files
    for path in [comparison.image1_path, comparison.image2_path, comparison.gif_path,
                comparison.color_diff1_path, comparison.color_diff2_path,
                comparison.gray_diff1_path, comparison.gray_diff2_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    db.session.delete(comparison)
    db.session.commit()

    flash('Comparison deleted successfully')
    return redirect(url_for('dashboard'))

@app.template_filter('file_exists')
def file_exists_filter(path):
    return path and os.path.exists(path)
# Add this to your app.py file
# Replace the existing admin_dashboard route with this corrected version
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get all comparisons
    comparisons = Comparison.query.all()  # Changed from ImageComparison to Comparison

    # Get all users
    users = User.query.all()

    # Add username attribute to each comparison object
    for comparison in comparisons:
        user = User.query.get(comparison.user_id)
        comparison.username = user.username if user else "Unknown"

    # Count comparisons per user
    users_with_counts = []
    comparisons_by_user = {}

    for user in users:
        user_comparisons = Comparison.query.filter_by(user_id=user.id).all()  # Changed from ImageComparison to Comparison
        users_with_counts.append((user, len(user_comparisons)))
        comparisons_by_user[user.username] = user_comparisons

    # Calculate statistics
    stats = {
        'total_comparisons': len(comparisons),
        'total_users': len(users),
        'public_comparisons': len([c for c in comparisons if c.is_public]),
        'private_comparisons': len([c for c in comparisons if not c.is_public])
    }

    return render_template(
        'admin_dashboard.html',
        stats=stats,
        users_with_counts=users_with_counts,
        comparisons=comparisons,
        comparisons_by_user=comparisons_by_user
    )



# Add this route to your app.py file

@app.route('/api/admin/stats')
@login_required
def admin_stats_api():
    if current_user.role != 'admin':
        return jsonify({'error': 'Not authorized'}), 403

    # Get comparison stats
    total_comparisons = Comparison.query.count()
    public_comparisons = Comparison.query.filter_by(is_public=True).count()
    private_comparisons = total_comparisons - public_comparisons

    # Get user stats
    total_users = User.query.count()
    admin_users = User.query.filter_by(role='admin').count()
    regular_users = total_users - admin_users

    # Get recent activity (last 7 days)
    one_week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    recent_comparisons = Comparison.query.filter(Comparison.created_at >= one_week_ago).count()

    # Activity by day (last 7 days)
    daily_activity = []
    for i in range(7):
        day = datetime.datetime.utcnow() - datetime.timedelta(days=i)
        day_start = datetime.datetime(day.year, day.month, day.day, 0, 0, 0)
        day_end = datetime.datetime(day.year, day.month, day.day, 23, 59, 59)

        count = Comparison.query.filter(
            Comparison.created_at >= day_start,
            Comparison.created_at <= day_end
        ).count()

        daily_activity.append({
            'date': day_start.strftime('%Y-%m-%d'),
            'day': day_start.strftime('%a'),
            'count': count
        })

    # Top users by comparison count
    top_users = db.session.query(
        User.username,
        db.func.count(Comparison.id).label('count')
    ).join(
        Comparison, User.id == Comparison.user_id
    ).group_by(
        User.username
    ).order_by(
        db.func.count(Comparison.id).desc()
    ).limit(5).all()

    return jsonify({
        'comparison_stats': {
            'total': total_comparisons,
            'public': public_comparisons,
            'private': private_comparisons
        },
        'user_stats': {
            'total': total_users,
            'admin': admin_users,
            'regular': regular_users
        },
        'activity': {
            'recent': recent_comparisons,
            'daily': daily_activity
        },
        'top_users': [{'username': user[0], 'count': user[1]} for user in top_users]
    })
# Initialize the database
with app.app_context():
    db.create_all()

@app.context_processor
def inject_year():
    return {'current_year': datetime.datetime.now().year}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
