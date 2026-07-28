import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ---------- APP ----------
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# ---------- ENVIRONMENT VARIABLES ----------
DATABASE_URL = os.getenv('DATABASE_URL')

# ---------- FALLBACK: Local Development ----------
if not DATABASE_URL:
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///donations.db')

print(f"✅ DATABASE_URL: {'✓ Set' if DATABASE_URL else '✗ Not Set'}")

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
    utr = Column(String(100), nullable=False, unique=True)  # Transaction ID / UTR
    message = Column(Text, default='')
    status = Column(String(20), default='pending')  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Create tables
Base.metadata.create_all(engine)

# ============================================================
# FRONTEND ROUTES
# ============================================================
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/admin')
def serve_admin():
    return send_from_directory('.', 'admin.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# ============================================================
# API ROUTES
# ============================================================
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'db_configured': bool(DATABASE_URL)
    })

# ---------- GET APPROVED DONORS (सिर्फ Approved दिखेंगे) ----------
@app.route('/api/donors', methods=['GET'])
def get_approved_donors():
    session = SessionLocal()
    try:
        donors = session.query(Donation)\
            .filter(Donation.status == 'approved')\
            .order_by(Donation.created_at.desc())\
            .limit(30).all()
        
        result = [{
            'id': d.id,
            'name': d.name,
            'amount': d.amount,
            'message': d.message or '🙏 हरि बोल',
            'date': d.created_at.strftime('%d %b %Y, %I:%M %p')
        } for d in donors]
        return jsonify(result)
    finally:
        session.close()

# ---------- SUBMIT DONATION (Status = Pending) ----------
@app.route('/api/donate', methods=['POST'])
def submit_donation():
    data = request.get_json()
    name = data.get('name', '').strip()
    mobile = data.get('mobile', '').strip()
    amount = int(data.get('amount', 0))
    utr = data.get('utr', '').strip()
    message = data.get('message', '').strip()

    # Validation
    if not name or len(name) < 2:
        return jsonify({'error': 'कृपया सही नाम दर्ज करें'}), 400
    if not mobile or len(mobile) < 10 or not mobile.isdigit():
        return jsonify({'error': 'कृपया सही मोबाइल नंबर दर्ज करें'}), 400
    if amount <= 0:
        return jsonify({'error': 'कृपया सही राशि दर्ज करें'}), 400
    if not utr or len(utr) < 4:
        return jsonify({'error': 'कृपया सही UTR/Transaction ID दर्ज करें'}), 400

    # Check if UTR already exists
    session = SessionLocal()
    existing = session.query(Donation).filter(Donation.utr == utr).first()
    if existing:
        session.close()
        return jsonify({'error': 'यह UTR पहले से मौजूद है। कृपया सही UTR दर्ज करें।'}), 400

    # Save with pending status
    donation = Donation(
        name=name,
        mobile=mobile,
        amount=amount,
        utr=utr,
        message=message or '🙏 हरि बोल',
        status='pending'
    )
    session.add(donation)
    session.commit()
    session.close()

    return jsonify({
        'status': 'pending',
        'message': 'आपका दान सबमिट हो गया है। Admin द्वारा Approve होने के बाद यह दिखेगा। 🙏'
    })

# ---------- ADMIN: GET ALL DONATIONS ----------
@app.route('/api/admin/donations', methods=['GET'])
def admin_get_all():
    session = SessionLocal()
    try:
        donors = session.query(Donation)\
            .order_by(Donation.created_at.desc())\
            .all()
        
        result = [{
            'id': d.id,
            'name': d.name,
            'mobile': d.mobile,
            'amount': d.amount,
            'utr': d.utr,
            'message': d.message or '',
            'status': d.status,
            'date': d.created_at.strftime('%d %b %Y, %I:%M %p')
        } for d in donors]
        return jsonify(result)
    finally:
        session.close()

# ---------- ADMIN: APPROVE DONATION ----------
@app.route('/api/admin/approve/<int:donation_id>', methods=['POST'])
def admin_approve(donation_id):
    session = SessionLocal()
    try:
        donation = session.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return jsonify({'error': 'Donation not found'}), 404
        
        if donation.status == 'approved':
            return jsonify({'message': 'Already approved'}), 200
        
        donation.status = 'approved'
        donation.updated_at = datetime.utcnow()
        session.commit()
        return jsonify({'status': 'approved', 'message': 'Donation approved successfully'})
    finally:
        session.close()

# ---------- ADMIN: REJECT DONATION ----------
@app.route('/api/admin/reject/<int:donation_id>', methods=['POST'])
def admin_reject(donation_id):
    session = SessionLocal()
    try:
        donation = session.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return jsonify({'error': 'Donation not found'}), 404
        
        if donation.status == 'rejected':
            return jsonify({'message': 'Already rejected'}), 200
        
        donation.status = 'rejected'
        donation.updated_at = datetime.utcnow()
        session.commit()
        return jsonify({'status': 'rejected', 'message': 'Donation rejected'})
    finally:
        session.close()

# ---------- ADMIN: DELETE DONATION ----------
@app.route('/api/admin/delete/<int:donation_id>', methods=['DELETE'])
def admin_delete(donation_id):
    session = SessionLocal()
    try:
        donation = session.query(Donation).filter(Donation.id == donation_id).first()
        if not donation:
            return jsonify({'error': 'Donation not found'}), 404
        
        session.delete(donation)
        session.commit()
        return jsonify({'message': 'Donation deleted successfully'})
    finally:
        session.close()

# ============================================================
# RUN SERVER
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
