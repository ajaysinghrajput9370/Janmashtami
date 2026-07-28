import os
import razorpay
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# ---------- LOAD ENV ----------
load_dotenv()

# ---------- APP CONFIG ----------
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# ---------- DATABASE (Neon DB - PostgreSQL) ----------
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("⚠️ DATABASE_URL not set. Using SQLite as fallback.")
    DATABASE_URL = 'sqlite:///donations.db'

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ---------- DONATION TABLE ----------
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

# Create tables if not exist
Base.metadata.create_all(engine)

# ---------- RAZORPAY ----------
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    print("⚠️ Razorpay keys not set. Payment will not work.")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ============================================================
# FRONTEND ROUTE
# ============================================================
@app.route('/')
def serve_index():
    """Serve the main index.html page."""
    return send_from_directory('.', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files."""
    return send_from_directory('static', path)


# ============================================================
# API ROUTES
# ============================================================
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


@app.route('/api/donors', methods=['GET'])
def get_donors():
    """Fetch latest 30 donors from database."""
    session = SessionLocal()
    try:
        donors = session.query(Donation).order_by(
            Donation.created_at.desc()
        ).limit(30).all()
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
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/create-order', methods=['POST'])
def create_order():
    """Create a Razorpay order for the donation."""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        amount = int(data.get('amount', 0))

        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if amount <= 0:
            return jsonify({'error': 'Valid amount is required'}), 400

        # Create order
        order_data = {
            'amount': amount * 100,  # paise
            'currency': 'INR',
            'receipt': f'receipt_{name}_{int(datetime.now().timestamp())}',
            'notes': {'name': name}
        }
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
    """Verify Razorpay payment signature and save to DB."""
    try:
        data = request.get_json()
        payment_id = data.get('razorpay_payment_id')
        order_id = data.get('razorpay_order_id')
        signature = data.get('razorpay_signature')
        name = data.get('name', '').strip()
        amount = int(data.get('amount', 0))
        message = data.get('message', '').strip()

        # Verify signature
        params = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        client.utility.verify_payment_signature(params)

        # Save to database
        session = SessionLocal()
        try:
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
            return jsonify({'status': 'success', 'message': 'Payment verified and saved'})
        except Exception as e:
            session.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            session.close()

    except razorpay.errors.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# RUN SERVER
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
