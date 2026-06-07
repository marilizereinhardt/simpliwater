import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import json

app = Flask(__name__)

# Database config
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'simpliwater-dev-key')

db = SQLAlchemy(app)

# ── MODELS ──────────────────────────────────────────────────────

class Client(db.Model):
    __tablename__ = 'clients'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    contact     = db.Column(db.String(200))
    phone       = db.Column(db.String(50))
    email       = db.Column(db.String(200))
    vat         = db.Column(db.String(50))
    brn         = db.Column(db.String(50))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    addresses   = db.relationship('ClientAddress', backref='client', lazy=True, cascade='all, delete-orphan')
    quotes      = db.relationship('Quote', backref='client', lazy=True)

class ClientAddress(db.Model):
    __tablename__ = 'client_addresses'
    id        = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    address   = db.Column(db.String(500), nullable=False)

class Quote(db.Model):
    __tablename__ = 'quotes'
    id           = db.Column(db.Integer, primary_key=True)
    quote_number = db.Column(db.String(20), unique=True, nullable=False)
    job_type     = db.Column(db.String(20))
    client_id    = db.Column(db.Integer, db.ForeignKey('clients.id'))
    site_address = db.Column(db.String(500))
    scope        = db.Column(db.Text)
    quote_date   = db.Column(db.Date, default=date.today)
    valid_until  = db.Column(db.Date)
    status       = db.Column(db.String(30), default='draft')
    pay_terms    = db.Column(db.String(200), default='75% upfront · 25% of project commencement (COD)')
    pay_notes    = db.Column(db.String(200))
    tc_standard  = db.Column(db.Text)
    tc_extra     = db.Column(db.Text)
    overall_disc = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    line_items   = db.relationship('LineItem', backref='quote', lazy=True, cascade='all, delete-orphan')

class LineItem(db.Model):
    __tablename__ = 'line_items'
    id          = db.Column(db.Integer, primary_key=True)
    quote_id    = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    quantity    = db.Column(db.Float, default=1)
    unit_rate   = db.Column(db.Float, default=0)
    disc_enabled= db.Column(db.Boolean, default=False)
    disc_pct    = db.Column(db.Float, default=0)
    sort_order  = db.Column(db.Integer, default=0)

class PriceScheduleItem(db.Model):
    __tablename__ = 'price_schedule'
    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    unit_rate   = db.Column(db.Float, default=0)
    sort_order  = db.Column(db.Integer, default=0)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ── ROUTES ──────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('simpliwater_final.html')

@app.route('/api/init', methods=['POST'])
def init_db():
    db.create_all()
    _seed_price_schedule()
    _seed_clients()
    return jsonify({'status': 'ok', 'message': 'Database initialised'})

def _seed_price_schedule():
    if PriceScheduleItem.query.count() > 0:
        return
    items = [
        ('Travel', 1500), ('Site Establishment (Setup & Cleanup)', 3500),
        ('Drain Prep', 6850), ('CIPP — DN100 Rehabilitation 3mm PVC Felt Drag and Orange Calibration Hose', 0),
        ('Consumables', 0), ('Plant and Equipment on Site', 6500),
        ('Labour (Day Rate)', 22500), ('EBC DN50', 2350), ('EBC DN75', 3200),
        ('EBC DN100', 4100), ('Labour', 22500), ('General Plumbing', 0),
        ('Post CCTV Inspection and Report', 0), ('CCTV Inspection', 0),
        ('Gas Leak Detection', 0), ('Radio Detection (Pipe Locating)', 0),
        ('CCTV Inspection & Radio Detection (Pipe Locating)', 0),
        ('CIPP — DN50 — Brawoliner', 0), ('Reinstatement of Junction / Ts', 0),
        ('Quick Dry Service', 0), ('Acoustic Leak Detection', 0),
        ('Gas Leak Detection (per Hour Rate)', 0), ('High Pressure & Speed Drain Cleaning', 0),
        ('Material', 0), ('Outsourced Equipment Rental', 0), ('Overpumping — MH to MH', 0),
        ('Water Leak Investigation', 0), ('Tracer Gas per Hour — Rate', 0),
        ('Acoustic Leak Detection per Hour — Rate', 0), ('Biodyne 301 — Waste Treatment', 0),
        ('DN50 Superflex 2mm Felt Liner', 0), ('Patch Repair — Sectional DN75', 0),
        ('Waterproofing', 0), ('CIPP Patch Repair DN150 (Sectional)', 0),
        ('Thermal Image Report and Survey', 0),
    ]
    for i, (desc, rate) in enumerate(items):
        db.session.add(PriceScheduleItem(description=desc, unit_rate=rate, sort_order=i))
    db.session.commit()

def _seed_clients():
    if Client.query.count() > 0:
        return
    clients = [
        {'name':'Tim Straw','contact':'Tim Straw','phone':'(+230) 5458 0126','email':'tim.straw@email.com','vat':'','brn':'',
         'addresses':['Calodyne, Mauritius','Villa 4, Anse La Raie, Mauritius']},
        {'name':'Residencia Belle Vue','contact':'Belle Vue Management','phone':'(+230) 5912 3456','email':'bv@bellevue.mu','vat':'28091234','brn':'C221XXXXX',
         'addresses':['Residencia Belle Vue, Grand Baie','Site B — Pool Area, Grand Baie']},
        {'name':'Tamarin Villas','contact':'Tamarin Villas Office','phone':'(+230) 5867 9100','email':'info@tamarinvillas.mu','vat':'','brn':'',
         'addresses':['Tamarin Villas, Tamarin','Block C, Tamarin','Swimming Pool Area, Tamarin']},
    ]
    for c in clients:
        client = Client(name=c['name'],contact=c['contact'],phone=c['phone'],email=c['email'],vat=c['vat'],brn=c['brn'])
        db.session.add(client)
        db.session.flush()
        for addr in c['addresses']:
            db.session.add(ClientAddress(client_id=client.id, address=addr))
    db.session.commit()

# ── CLIENT API ───────────────────────────────────────────────────

@app.route('/api/clients', methods=['GET'])
def get_clients():
    clients = Client.query.order_by(Client.name).all()
    return jsonify([{
        'id': c.id, 'name': c.name, 'contact': c.contact,
        'phone': c.phone, 'email': c.email, 'vat': c.vat, 'brn': c.brn,
        'addresses': [a.address for a in c.addresses]
    } for c in clients])

@app.route('/api/clients', methods=['POST'])
def create_client():
    data = request.json
    client = Client(
        name=data.get('name',''), contact=data.get('contact',''),
        phone=data.get('phone',''), email=data.get('email',''),
        vat=data.get('vat',''), brn=data.get('brn','')
    )
    db.session.add(client)
    db.session.flush()
    for addr in data.get('addresses', []):
        db.session.add(ClientAddress(client_id=client.id, address=addr))
    db.session.commit()
    return jsonify({'id': client.id, 'name': client.name}), 201

@app.route('/api/clients/<int:cid>/addresses', methods=['POST'])
def add_address(cid):
    data = request.json
    addr = ClientAddress(client_id=cid, address=data.get('address',''))
    db.session.add(addr)
    db.session.commit()
    return jsonify({'id': addr.id, 'address': addr.address}), 201

# ── QUOTE API ────────────────────────────────────────────────────

@app.route('/api/quotes', methods=['GET'])
def get_quotes():
    quotes = Quote.query.order_by(Quote.created_at.desc()).all()
    return jsonify([_quote_summary(q) for q in quotes])

@app.route('/api/quotes/<int:qid>', methods=['GET'])
def get_quote(qid):
    q = Quote.query.get_or_404(qid)
    return jsonify(_quote_full(q))

@app.route('/api/quotes', methods=['POST'])
def save_quote():
    data = request.json
    qnum = data.get('quote_number','')
    existing = Quote.query.filter_by(quote_number=qnum).first()
    if existing:
        q = existing
    else:
        q = Quote(quote_number=qnum)
        db.session.add(q)

    q.job_type     = data.get('job_type')
    q.client_id    = data.get('client_id')
    q.site_address = data.get('site_address','')
    q.scope        = data.get('scope','')
    q.quote_date   = _parse_date(data.get('quote_date'))
    q.valid_until  = _parse_date(data.get('valid_until'))
    q.status       = data.get('status','draft')
    q.pay_terms    = data.get('pay_terms','')
    q.pay_notes    = data.get('pay_notes','')
    q.tc_standard  = data.get('tc_standard','')
    q.tc_extra     = data.get('tc_extra','')
    q.overall_disc = data.get('overall_disc', 0)
    q.total_amount = data.get('total_amount', 0)

    db.session.flush()
    LineItem.query.filter_by(quote_id=q.id).delete()
    for i, item in enumerate(data.get('line_items', [])):
        db.session.add(LineItem(
            quote_id=q.id, description=item.get('description',''),
            quantity=item.get('quantity',1), unit_rate=item.get('unit_rate',0),
            disc_enabled=item.get('disc_enabled',False),
            disc_pct=item.get('disc_pct',0), sort_order=i
        ))
    db.session.commit()
    return jsonify({'id': q.id, 'quote_number': q.quote_number}), 200

@app.route('/api/quotes/<int:qid>/status', methods=['PATCH'])
def update_status(qid):
    q = Quote.query.get_or_404(qid)
    if q.status in ('accepted', 'rejected'):
        return jsonify({'error': 'Locked'}), 403
    q.status = request.json.get('status', q.status)
    db.session.commit()
    return jsonify({'status': q.status})

# ── PRICE SCHEDULE API ───────────────────────────────────────────

@app.route('/api/price-schedule', methods=['GET'])
def get_price_schedule():
    items = PriceScheduleItem.query.order_by(PriceScheduleItem.sort_order).all()
    return jsonify([{'id':i.id,'description':i.description,'unit_rate':i.unit_rate} for i in items])

@app.route('/api/price-schedule/<int:iid>', methods=['PATCH'])
def update_price(iid):
    item = PriceScheduleItem.query.get_or_404(iid)
    item.unit_rate = request.json.get('unit_rate', item.unit_rate)
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'id': item.id, 'unit_rate': item.unit_rate})

@app.route('/api/price-schedule', methods=['POST'])
def add_price_item():
    data = request.json
    item = PriceScheduleItem(
        description=data.get('description',''),
        unit_rate=data.get('unit_rate',0),
        sort_order=PriceScheduleItem.query.count()
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'id':item.id,'description':item.description,'unit_rate':item.unit_rate}), 201

# ── HELPERS ──────────────────────────────────────────────────────

def _parse_date(d):
    if not d: return None
    try: return datetime.strptime(d, '%Y-%m-%d').date()
    except: return None

def _quote_summary(q):
    return {
        'id': q.id, 'quote_number': q.quote_number, 'job_type': q.job_type,
        'client_name': q.client.name if q.client else '',
        'quote_date': q.quote_date.strftime('%d/%m/%Y') if q.quote_date else '',
        'status': q.status, 'total_amount': q.total_amount,
        'locked': q.status in ('accepted','rejected')
    }

def _quote_full(q):
    s = _quote_summary(q)
    s.update({
        'client_id': q.client_id, 'site_address': q.site_address,
        'scope': q.scope, 'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
        'quote_date_raw': q.quote_date.strftime('%Y-%m-%d') if q.quote_date else '',
        'pay_terms': q.pay_terms, 'pay_notes': q.pay_notes,
        'tc_standard': q.tc_standard, 'tc_extra': q.tc_extra,
        'overall_disc': q.overall_disc,
        'line_items': [{'description':li.description,'quantity':li.quantity,'unit_rate':li.unit_rate,
                        'disc_enabled':li.disc_enabled,'disc_pct':li.disc_pct} for li in q.line_items]
    })
    return s

if __name__ == '__main__':
    app.run(debug=True)
