from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from database import db, User, Item, Bill, BillItem, StockHistory
from datetime import datetime
import bcrypt
import qrcode
import io
import os

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../database/shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'

db.init_app(app)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='cashier').first():
        hashed = bcrypt.hashpw(b'cashier123', bcrypt.gensalt()).decode()
        db.session.add(User(username='cashier', password=hashed, role='cashier'))
    if not User.query.filter_by(username='admin').first():
        hashed = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
        db.session.add(User(username='admin', password=hashed, role='admin'))
    db.session.commit()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and bcrypt.checkpw(data['password'].encode(), user.password.encode()):
        if (data['role'] == 'cashier' and user.role == 'cashier') or \
           (data['role'] == 'admin' and user.role == 'admin'):
            return jsonify({'success': True, 'user': {'id': user.id, 'username': user.username, 'role': user.role}})
    return jsonify({'success': False, 'message': 'Invalid credentials or role'}), 401

@app.route('/api/items', methods=['GET'])
def get_items():
    search = request.args.get('search', '')
    items = Item.query.filter(Item.name.contains(search)).all()
    return jsonify([{
        'id': item.id, 'name': item.name, 'price': item.price,
        'stock_qty': item.stock_qty, 'category': item.category,
        'qr_code': item.qr_code
    } for item in items])

@app.route('/api/items', methods=['POST'])
def add_item():
    data = request.json
    qr_code = f"ITEM-{Item.query.count() + 1}"
    item = Item(
        name=data['name'], price=data['price'],
        stock_qty=data.get('stock_qty', 0),
        category=data.get('category', 'General'),
        qr_code=qr_code
    )
    db.session.add(item)
    db.session.commit()
    
    if item.stock_qty > 0:
        db.session.add(StockHistory(
            item_id=item.id, change_type='add',
            quantity_change=item.stock_qty,
            reason='Initial stock', user_id=data.get('user_id')
        ))
    db.session.commit()
    return jsonify({'success': True, 'item': {'id': item.id, 'qr_code': qr_code}})

@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    item = Item.query.get_or_404(item_id)
    data = request.json
    item.name = data.get('name', item.name)
    item.price = data.get('price', item.price)
    old_stock = item.stock_qty
    item.stock_qty = data.get('stock_qty', item.stock_qty)
    item.category = data.get('category', item.category)
    
    if item.stock_qty != old_stock:
        change = item.stock_qty - old_stock
        db.session.add(StockHistory(
            item_id=item.id,
            change_type='add' if change > 0 else 'remove',
            quantity_change=abs(change),
            reason=data.get('reason', 'Stock adjustment'),
            user_id=data.get('user_id')
        ))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/qr/<qr_code>')
def generate_qr(qr_code):
    qr = qrcode.make(f"{qr_code}")
    buf = io.BytesIO()
    qr.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/bills', methods=['POST'])
def create_bill():
    data = request.json
    bill = Bill(
        cashier_id=data['cashier_id'],
        total_amount=data['total_amount'],
        payment_method=data['payment_method']
    )
    db.session.add(bill)
    db.session.flush()
    
    for item_data in data['items']:
        bill_item = BillItem(
            bill_id=bill.id,
            item_id=item_data['item_id'],
            quantity=item_data['quantity'],
            price_at_sale=item_data['price']
        )
        db.session.add(bill_item)
        
        item = Item.query.get(item_data['item_id'])
        item.stock_qty -= item_data['quantity']
        
        db.session.add(StockHistory(
            item_id=item.id, change_type='sale',
            quantity_change=item_data['quantity'],
            reason=f'Bill #{bill.id}', user_id=data['cashier_id']
        ))
    db.session.commit()
    return jsonify({'success': True, 'bill_id': bill.id})

@app.route('/api/bills', methods=['GET'])
def get_bills():
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    bills = Bill.query.order_by(Bill.created_at.desc())
    
    if search:
        bills = bills.filter(Bill.id.contains(search))
    if start_date:
        bills = bills.filter(Bill.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        bills = bills.filter(Bill.created_at <= datetime.fromisoformat(end_date))
    
    result = []
    for bill in bills.limit(100).all():
        bill_items = []
        for bi in bill.items:
            bill_items.append({
                'item_name': bi.item.name,
                'quantity': bi.quantity,
                'price': bi.price_at_sale
            })
        result.append({
            'id': bill.id,
            'cashier_id': bill.cashier_id,
            'total_amount': bill.total_amount,
            'payment_method': bill.payment_method,
            'created_at': bill.created_at.isoformat(),
            'items': bill_items
        })
    return jsonify(result)

@app.route('/api/stock-history', methods=['GET'])
def get_stock_history():
    item_id = request.args.get('item_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    history = StockHistory.query.order_by(StockHistory.timestamp.desc())
    
    if item_id:
        history = history.filter_by(item_id=item_id)
    if start_date:
        history = history.filter(StockHistory.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        history = history.filter(StockHistory.timestamp <= datetime.fromisoformat(end_date))
    
    result = []
    for h in history.limit(200).all():
        result.append({
            'id': h.id,
            'item_name': h.item.name,
            'change_type': h.change_type,
            'quantity_change': h.quantity_change,
            'reason': h.reason,
            'timestamp': h.timestamp.isoformat()
        })
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, port=5000)