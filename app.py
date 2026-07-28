import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv('SECRET_KEY', 'janmashtami-secret-key-2026')
CORS(app)

# ---------- CONFIG ----------
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///donations.db')

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
TARGET_AMOUNT = 20000

# Upload config
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

print(f"✅ DATABASE_URL: {'✓ Set' if DATABASE_URL else '✗ Not Set'}")
print(f"✅ TARGET: ₹{TARGET_AMOUNT:,}")

# ---------- DATABASE ----------
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Donation(Base):
    __tablename__ = 'donations'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    mobile = Column(String(15), nullable=False)
    amount = Column(Integer, nullable=False)
    screenshot = Column(String(255), default='')  # स्क्रीनशॉट फाइल पाथ
    message = Column(Text, default='')
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(engine)

# ============================================================
# FRONTEND ROUTES
# ============================================================
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/admin')
def serve_admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return send_from_directory('.', 'admin.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('serve_admin'))
        else:
            return '''
                <!DOCTYPE html>
                <html><head><title>Login Failed</title></head>
                <body style="background:linear-gradient(135deg,#FF6B35,#FF4081);color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;">
                    <h2>❌ Invalid Credentials</h2>
                    <p><a href="/admin/login" style="color:#FFD700;">Try Again</a></p>
                </body></html>
            ''', 401
    return '''
        <!DOCTYPE html>
        <html>
        <head><title>Admin Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body {
                background: linear-gradient(135deg, #FF6B35, #FF4081, #7B2FBE);
                font-family: 'Segoe UI', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: 20px;
            }
            .login-box {
                background: rgba(255,255,255,0.12);
                backdrop-filter: blur(20px);
                padding: 40px 30px;
                border-radius: 28px;
                border: 1px solid rgba(255,255,255,0.15);
                width: 100%;
                max-width: 380px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 {
                font-size: 1.8rem; font-weight: 800;
                color: #fff;
                text-align: center;
                margin-bottom: 24px;
                text-shadow: 0 2px 20px rgba(0,0,0,0.2);
            }
            label { display: block; font-size: 0.8rem; color: rgba(255,255,255,0.7); margin-bottom: 4px; }
            input {
                width: 100%; padding: 12px 16px; border-radius: 60px;
                border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.08);
                color: #fff; font-size: 0.9rem; outline: none; margin-bottom: 16px;
            }
            input::placeholder { color: rgba(255,255,255,0.3); }
            input:focus { border-color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.12); }
            button {
                width: 100%; padding: 14px; border: none; border-radius: 60px;
                background: linear-gradient(135deg, #FFD700, #FF6B35);
                color: #fff; font-weight: 700; font-size: 1rem; cursor: pointer;
                transition: 0.3s;
            }
            button:hover { transform: scale(1.02); box-shadow: 0 8px 30px rgba(255,215,0,0.3); }
            .back-link {
                display: block; text-align: center; margin-top: 16px;
                color: rgba(255,255,255,0.6); font-size: 0.8rem; text-decoration: none;
            }
            .back-link:hover { color: #FFD700; }
        </style>
        </head>
        <body>
            <div class="login-box">
                <h1>🙏 Admin Login</h1>
                <form method="POST">
                    <label>Username</label>
                    <input type="text" name="username" placeholder="Enter username" required>
                    <label>Password</label>
                    <input type="password" name="password" placeholder="Enter password" required>
                    <button type="submit">🔐 Login</button>
                </form>
                <a href="/" class="back-link">← Homepage</a>
            </div>
        </body>
        </html>
    '''

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/api/target')
def get_target():
    return jsonify({'target': TARGET_AMOUNT})

# ---------- API ROUTES ----------
@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/donors')
def get_approved_donors():
    session_db = SessionLocal()
    try:
        donors = session_db.query(Donation).filter(Donation.status == 'approved')\
            .order_by(Donation.created_at.desc()).limit(30).all()
        result = [{
            'id': d.id,
            'name': d.name,
            'amount': d.amount,
            'message': d.message or '🙏 हरि बोल',
            'date': d.created_at.strftime('%d %b %Y, %I:%M %p')
        } for d in donors]
        return jsonify(result)
    finally:
        session_db.close()

@app.route('/api/donate', methods=['POST'])
def submit_donation():
    name = request.form.get('name', '').strip()
    mobile = request.form.get('mobile', '').strip()
    amount = int(request.form.get('amount', 0))
    message = request.form.get('message', '').strip()
    screenshot = request.files.get('screenshot')

    # Validations
    if not name or len(name) < 2:
        return jsonify({'error': 'कृपया सही नाम दर्ज करें'}), 400
    if not mobile or len(mobile) < 10 or not mobile.isdigit():
        return jsonify({'error': 'कृपया सही मोबाइल नंबर दर्ज करें'}), 400
    if amount <= 0:
        return jsonify({'error': 'कृपया सही राशि दर्ज करें'}), 400

    # Handle screenshot upload (optional)
    screenshot_path = ''
    if screenshot and screenshot.filename:
        if allowed_file(screenshot.filename):
            filename = f"{uuid.uuid4().hex}_{secure_filename(screenshot.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            screenshot.save(filepath)
            screenshot_path = f"/static/uploads/{filename}"
        else:
            return jsonify({'error': 'कृपया PNG, JPG या JPEG फाइल अपलोड करें'}), 400

    session_db = SessionLocal()
    donation = Donation(
        name=name,
        mobile=mobile,
        amount=amount,
        screenshot=screenshot_path,
        message=message or '🙏 हरि बोल',
        status='pending'
    )
    session_db.add(donation)
    session_db.commit()
    session_db.close()

    return jsonify({
        'status': 'pending',
        'message': 'आपका दान सबमिट हो गया है। Admin द्वारा Approve होने के बाद यह दिखेगा। 🙏'
    })

@app.route('/api/admin/donations')
def admin_get_all():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    session_db = SessionLocal()
    try:
        donors = session_db.query(Donation).order_by(Donation.created_at.desc()).all()
        result = [{
            'id': d.id,
            'name': d.name,
            'mobile': d.mobile,
            'amount': d.amount,
            'screenshot': d.screenshot,
            'message': d.message or '',
            'status': d.status,
            'date': d.created_at.strftime('%d %b %Y, %I:%M %p')
        } for d in donors]
        return jsonify(result)
    finally:
        session_db.close()

@app.route('/api/admin/approve/<int:donation_id>', methods=['POST'])
def admin_approve(donation_id):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    session_db = SessionLocal()
    try:
        donation = session_db.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return jsonify({'error': 'Not found'}), 404
        if donation.status == 'approved':
            return jsonify({'message': 'Already approved'})
        donation.status = 'approved'
        donation.updated_at = datetime.utcnow()
        session_db.commit()
        return jsonify({'status': 'approved', 'message': '✅ Approved'})
    finally:
        session_db.close()

@app.route('/api/admin/reject/<int:donation_id>', methods=['POST'])
def admin_reject(donation_id):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    session_db = SessionLocal()
    try:
        donation = session_db.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return jsonify({'error': 'Not found'}), 404
        if donation.status == 'rejected':
            return jsonify({'message': 'Already rejected'})
        donation.status = 'rejected'
        donation.updated_at = datetime.utcnow()
        session_db.commit()
        return jsonify({'status': 'rejected', 'message': '❌ Rejected'})
    finally:
        session_db.close()

@app.route('/api/admin/delete/<int:donation_id>', methods=['DELETE'])
def admin_delete(donation_id):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    session_db = SessionLocal()
    try:
        donation = session_db.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return jsonify({'error': 'Not found'}), 404
        # Delete screenshot file if exists
        if donation.screenshot:
            filepath = donation.screenshot.lstrip('/')
            fullpath = os.path.join(os.getcwd(), filepath)
            if os.path.exists(fullpath):
                os.remove(fullpath)
        session_db.delete(donation)
        session_db.commit()
        return jsonify({'message': '🗑️ Deleted'})
    finally:
        session_db.close()

# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
