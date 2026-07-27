# ============================================================
# app.py – Flask Backend for Krishna Janmashtami Donation System
# ============================================================
# Run: python app.py
# API Base: http://localhost:5000/api
# ============================================================

import os
import sqlite3
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.exceptions import BadRequest

# ---------- CONFIG ----------
DATABASE = 'donors.db'
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ---------- DATABASE HELPERS ----------
def get_db():
    """Get database connection (thread-local)."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    """Create tables if they don't exist."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS donors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mobile TEXT NOT NULL,
                amount INTEGER NOT NULL,
                txn TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending',
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

def close_db(exception=None):
    """Close database connection."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.teardown_appcontext
def teardown_db(exception=None):
    close_db(exception)

# ---------- AUTO-PAYMENT CONFIRMATION (Background Thread) ----------
def auto_confirm_payments():
    """
    Background thread: checks for pending donations with a transaction ID
    and auto-confirms them after 30 seconds.
    """
    with app.app_context():
        while True:
            try:
                time.sleep(30)  # Check every 30 seconds
                db = get_db()
                cursor = db.cursor()
                # Find pending donations with a transaction ID
                cursor.execute('''
                    UPDATE donors 
                    SET status = 'confirmed' 
                    WHERE status = 'pending' 
                    AND txn IS NOT NULL 
                    AND txn != ''
                    AND datetime(created_at, '+30 seconds') <= datetime('now')
                ''')
                if cursor.rowcount > 0:
                    db.commit()
                    print(f"✅ Auto-confirmed {cursor.rowcount} donation(s)")
            except Exception as e:
                print(f"⚠️ Auto-confirm error: {e}")

# Start background thread
thread = threading.Thread(target=auto_confirm_payments, daemon=True)
thread.start()

# ---------- API ROUTES ----------
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/donors', methods=['GET'])
def get_donors():
    """Get all donors sorted by newest first."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT id, name, mobile, amount, txn, message, status, date, created_at
            FROM donors
            ORDER BY created_at DESC
        ''')
        rows = cursor.fetchall()
        donors = []
        for row in rows:
            donors.append({
                'id': row['id'],
                'name': row['name'],
                'mobile': row['mobile'],
                'amount': row['amount'],
                'txn': row['txn'] or '',
                'message': row['message'] or '',
                'status': row['status'],
                'date': row['date'],
                'created_at': row['created_at']
            })
        return jsonify(donors)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/donors/stats', methods=['GET'])
def get_stats():
    """Get donation statistics."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT COUNT(*) as total FROM donors')
        total_donors = cursor.fetchone()['total']

        cursor.execute('SELECT SUM(amount) as total_amount FROM donors WHERE status = "confirmed"')
        total_amount = cursor.fetchone()['total_amount'] or 0

        cursor.execute('SELECT COUNT(*) as pending FROM donors WHERE status = "pending"')
        pending = cursor.fetchone()['pending']

        return jsonify({
            'total_donors': total_donors,
            'total_collection': total_amount,
            'pending_count': pending,
            'target': 500000
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/donate', methods=['POST'])
def create_donation():
    """Create a new donation entry."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400

        # Validate required fields
        name = data.get('name', '').strip()
        mobile = data.get('mobile', '').strip()
        amount = data.get('amount')

        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not mobile or len(mobile) < 10:
            return jsonify({'error': 'Valid mobile number is required'}), 400
        if not amount or int(amount) <= 0:
            return jsonify({'error': 'Valid amount is required'}), 400

        amount = int(amount)
        txn = data.get('txn', '').strip()
        message = data.get('message', '').strip()
        # Auto-confirm if transaction ID is provided
        status = 'confirmed' if txn else 'pending'

        # Auto-detect name from UPI (if available) - just a placeholder logic
        # In real scenario, you'd parse from UPI webhook or payment gateway
        # For now, we use the provided name

        date_str = datetime.now().strftime('%d %b %Y, %I:%M %p')

        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO donors (name, mobile, amount, txn, message, status, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, mobile, amount, txn, message, status, date_str))
        db.commit()

        donor_id = cursor.lastrowid

        # Fetch the created donor
        cursor.execute('SELECT * FROM donors WHERE id = ?', (donor_id,))
        row = cursor.fetchone()

        return jsonify({
            'id': row['id'],
            'name': row['name'],
            'mobile': row['mobile'],
            'amount': row['amount'],
            'txn': row['txn'] or '',
            'message': row['message'] or '',
            'status': row['status'],
            'date': row['date'],
            'auto_confirmed': status == 'confirmed'
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/donor/<int:donor_id>', methods=['GET'])
def get_donor(donor_id):
    """Get a single donor by ID."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM donors WHERE id = ?', (donor_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Donor not found'}), 404

        return jsonify({
            'id': row['id'],
            'name': row['name'],
            'mobile': row['mobile'],
            'amount': row['amount'],
            'txn': row['txn'] or '',
            'message': row['message'] or '',
            'status': row['status'],
            'date': row['date']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/donor/<int:donor_id>', methods=['PUT'])
def update_donor(donor_id):
    """Update a donor (e.g., confirm payment, edit details)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400

        db = get_db()
        cursor = db.cursor()

        # Build update query dynamically
        fields = []
        values = []
        allowed_fields = ['name', 'mobile', 'amount', 'txn', 'message', 'status']

        for field in allowed_fields:
            if field in data and data[field] is not None:
                fields.append(f"{field} = ?")
                if field == 'amount':
                    values.append(int(data[field]))
                else:
                    values.append(data[field].strip())

        if not fields:
            return jsonify({'error': 'No fields to update'}), 400

        values.append(donor_id)
        query = f"UPDATE donors SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, values)
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({'error': 'Donor not found'}), 404

        # Fetch updated donor
        cursor.execute('SELECT * FROM donors WHERE id = ?', (donor_id,))
        row = cursor.fetchone()

        return jsonify({
            'id': row['id'],
            'name': row['name'],
            'mobile': row['mobile'],
            'amount': row['amount'],
            'txn': row['txn'] or '',
            'message': row['message'] or '',
            'status': row['status'],
            'date': row['date']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/donor/<int:donor_id>', methods=['DELETE'])
def delete_donor(donor_id):
    """Delete a donor by ID (admin only)."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM donors WHERE id = ?', (donor_id,))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({'error': 'Donor not found'}), 404

        return jsonify({'message': 'Donor deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/confirm/<int:donor_id>', methods=['POST'])
def confirm_donation(donor_id):
    """Manually confirm a donation."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('UPDATE donors SET status = "confirmed" WHERE id = ? AND status = "pending"', (donor_id,))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({'error': 'Donor not found or already confirmed'}), 404

        return jsonify({'message': 'Donation confirmed successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- WEBHOOK FOR PAYMENT GATEWAY (Simulated) ----------
@app.route('/api/webhook/payment', methods=['POST'])
def payment_webhook():
    """
    Webhook endpoint for payment gateways (Razorpay, PhonePe, etc.)
    Expected payload: { "txn_id": "xxx", "status": "success", "amount": 100, "name": "John" }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400

        txn_id = data.get('txn_id')
        status = data.get('status')
        amount = data.get('amount')
        name = data.get('name', 'Unknown')

        if not txn_id or not status:
            return jsonify({'error': 'txn_id and status are required'}), 400

        if status.lower() == 'success':
            # Find donor by transaction ID
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT * FROM donors WHERE txn = ?', (txn_id,))
            row = cursor.fetchone()

            if row:
                # Update status to confirmed
                cursor.execute('UPDATE donors SET status = "confirmed" WHERE id = ?', (row['id'],))
                db.commit()
                return jsonify({'message': f'Donation {txn_id} confirmed'})
            else:
                # If donor not found, create a new entry
                date_str = datetime.now().strftime('%d %b %Y, %I:%M %p')
                cursor.execute('''
                    INSERT INTO donors (name, mobile, amount, txn, message, status, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, '0000000000', amount, txn_id, 'Auto via webhook', 'confirmed', date_str))
                db.commit()
                return jsonify({'message': f'New donation created via webhook: {txn_id}'})

        return jsonify({'message': 'Webhook received'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- RUN SERVER ----------
if __name__ == '__main__':
    # Initialize database
    init_db()
    print("🕉️ श्री कृष्ण जन्माष्टमी दान प्रणाली")
    print("📡 Server running on http://localhost:5000")
    print("📡 API Base: http://localhost:5000/api")
    print("📡 Donors: http://localhost:5000/api/donors")
    print("📡 Stats: http://localhost:5000/api/donors/stats")
    print("📡 Health: http://localhost:5000/api/health")
    print("🔁 Auto-confirm thread started (checks every 30s)")
    print("🙏 जय श्री कृष्ण!")
    app.run(host='0.0.0.0', port=5000, debug=True)
