import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Database Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_public = db.Column(db.Boolean, default=False, nullable=False)

# --- Core Logic Routes ---

@app.route('/')
def home():
    if current_user.is_authenticated:
        # User Dashboard: Display only their personal memories by default
        my_posts = Post.query.filter_by(user_id=current_user.id).all()
        return render_template('index.html', title='My Diary', posts=my_posts)
    return render_template('index.html', title='Memoir')

@app.route('/explore')
def explore():
    # Public Feed: Display all entries marked public across the global platform
    public_posts = Post.query.filter_by(is_public=True).all()
    return render_template('explore.html', title='Shared Reflections', posts=public_posts)

@app.route('/user/<string:username>')
def user_public_posts(username):
    # Filtered Profile: Display all public posts belonging to a single unique user
    user = User.query.filter_by(username=username).first_or_404()
    public_posts = Post.query.filter_by(user_id=user.id, is_public=True).all()
    return render_template('user_posts.html', title=f"{username}'s Memories", posts=public_posts, username=username)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('That username is already taken. Try another!', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('home'))
    return render_template('register.html', title='Begin Your Journey')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
            
        flash('Incorrect username or password. Please try again.', 'error')
    return render_template('login.html', title='Welcome Back')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        is_public = 'is_public' in request.form
        
        new_blog_post = Post(title=title, content=content, author=current_user, is_public=is_public)
        db.session.add(new_blog_post)
        db.session.commit()
        flash('New diary entry recorded successfully!', 'success')
        return redirect(url_for('home'))
    return render_template('new_post.html', title='Write Memories') 

@app.route('/post/<int:post_id>')
def show_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('home'))
    return render_template('post.html', title=post.title, post=post)

@app.route('/post/<int:post_id>/make_public', methods=['POST'])
@login_required
def make_public(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('home'))
    
    post.is_public = True
    db.session.commit()
    flash('This memory has been shared with the public feed.', 'success')
    return redirect(url_for('show_post', post_id=post.id))

@app.route('/post/<int:post_id>/make_private', methods=['POST'])
@login_required
def make_private(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('home'))
    
    post.is_public = False
    db.session.commit()
    flash('This memory is now locked to other users.', 'success')
    return redirect(url_for('show_post', post_id=post.id))

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Security Guardrail: Prevent unauthorized editing
    if post.author != current_user:
        flash('Permission denied.', 'error')
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        post.is_public = 'is_public' in request.form
        
        db.session.commit()
        flash('Diary entry updated successfully!', 'success')
        return redirect(url_for('show_post', post_id=post.id))
        
    return render_template('update_post.html', title='Edit Memory', post=post)

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        flash('Permission denied.', 'error')
        return redirect(url_for('home'))
    db.session.delete(post)
    db.session.commit()
    flash('Memory successfully removed from your diary.', 'success')
    return redirect(url_for('home'))

@app.errorhandler(404)
def not_found(e):
    return render_template('not_found.html', title='Page Not Found'), 404

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
