import os
import razorpay
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ---------- APP ----------
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# ---------- ENVIRONMENT VARIABLES (Render से आएंगे) ----------
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
DATABASE_URL = os.getenv('DATABASE_URL')

# ---------- FALLBACK: Local Development के लिए .env ----------
if not DATABASE_URL:
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///donations.db')
    RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')

# ---------- CHECK (Production में यह Print न करें, सिर्फ Debug के लिए) ----------
print(f"✅ DATABASE_URL: {'✓ Set' if DATABASE_URL else '✗ Not Set'}")
print(f"✅ RAZORPAY_KEY_ID: {'✓ Set' if RAZORPAY_KEY_ID else '✗ Not Set'}")

# ---------- DATABASE (Neon DB) ----------
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Donation(Base):
    __tablename__ = 'donations'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    amount = Column(Integer, nullable=False)
    payment_id = Column(String(100), unique=True, nullable=False)
    order_id = Column(String(100))
    signature = Column(String(255))
    status = Column(String(20), default='success')
    message = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

# ---------- RAZORPAY CLIENT ----------
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ============================================================
# ROUTES
# ============================================================
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'razorpay_configured': bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET),
        'db_configured': bool(DATABASE_URL)
    })

@app.route('/api/donors', methods=['GET'])
def get_donors():
    session = SessionLocal()
    try:
        donors = session.query(Donation).order_by(Donation.created_at.desc()).limit(30).all()
        result = [{
            'id': d.id,
            'name': d.name,
            'amount': d.amount,
            'payment_id': d.payment_id,
            'status': d.status,
            'message': d.message or '🙏 हरि बोल',
            'date': d.created_at.strftime('%d %b %Y, %I:%M %p')
        } for d in donors]
        return jsonify(result)
    finally:
        session.close()

@app.route('/api/create-order', methods=['POST'])
def create_order():
    data = request.get_json()
    name = data.get('name', '').strip()
    amount = int(data.get('amount', 0))

    if not name or amount <= 0:
        return jsonify({'error': 'Name and valid amount required'}), 400

    order_data = {
        'amount': amount * 100,
        'currency': 'INR',
        'receipt': f'receipt_{name}_{int(datetime.now().timestamp())}',
        'notes': {'name': name}
    }
    try:
        order = client.order.create(order_data)
        return jsonify({
            'order_id': order['id'],
            'amount': amount,
            'name': name,
            'key': RAZORPAY_KEY_ID
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/verify-payment', methods=['POST'])
def verify_payment():
    data = request.get_json()
    payment_id = data.get('razorpay_payment_id')
    order_id = data.get('razorpay_order_id')
    signature = data.get('razorpay_signature')
    name = data.get('name')
    amount = int(data.get('amount', 0))
    message = data.get('message', '')

    params = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }

    try:
        client.utility.verify_payment_signature(params)

        session = SessionLocal()
        donation = Donation(
            name=name,
            amount=amount,
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
            status='success',
            message=message or '🙏 हरि बोल'
        )
        session.add(donation)
        session.commit()
        session.close()

        return jsonify({'status': 'success', 'message': 'Payment verified and saved'})

    except razorpay.errors.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
