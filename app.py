import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import sendgrid
from sendgrid.helpers.mail import Mail

app = Flask(__name__)

# ── CONFIG ───────────────────────────────────────────────────────
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'simpliwater-change-this-in-production')

SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'simpliwatermu@gmail.com')
APP_URL = os.environ.get('APP_URL', 'https://simpliwater.onrender.com')

db = SQLAlchemy(app)

# ── MODELS ───────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role          = db.Column(db.String(20), default='field')  # admin / field
    active        = db.Column(db.Boolean, default=True)
    perm_dashboard= db.Column(db.Boolean, default=True)
    perm_clients  = db.Column(db.Boolean, default=True)
    perm_quotes   = db.Column(db.Boolean, default=True)
    perm_jobs     = db.Column(db.Boolean, default=True)
    perm_reports  = db.Column(db.Boolean, default=True)
    perm_price    = db.Column(db.Boolean, default=False)
    perm_users    = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    reset_token   = db.Column(db.String(100))
    reset_expires = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def permissions(self):
        return {
            'dashboard': self.perm_dashboard,
            'clients':   self.perm_clients,
            'quotes':    self.perm_quotes,
            'jobs':      self.perm_jobs,
            'reports':   self.perm_reports,
            'price':     self.perm_price,
            'users':     self.perm_users,
        }

class Client(db.Model):
    __tablename__ = 'clients'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    company    = db.Column(db.String(200))
    contact    = db.Column(db.String(200))
    phone      = db.Column(db.String(50))
    email      = db.Column(db.String(200))
    vat        = db.Column(db.String(50))
    brn        = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    addresses  = db.relationship('ClientAddress', backref='client', lazy=True, cascade='all, delete-orphan')
    quotes     = db.relationship('Quote', backref='client', lazy=True)

class ClientAddress(db.Model):
    __tablename__ = 'client_addresses'
    id        = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    address   = db.Column(db.String(500))

class Quote(db.Model):
    __tablename__ = 'quotes'
    id           = db.Column(db.Integer, primary_key=True)
    quote_number = db.Column(db.String(50), unique=True, nullable=False)
    job_type     = db.Column(db.String(50))
    client_id    = db.Column(db.Integer, db.ForeignKey('clients.id'))
    site_address = db.Column(db.String(500))
    scope        = db.Column(db.Text)
    quote_date   = db.Column(db.Date)
    valid_until  = db.Column(db.Date)
    status       = db.Column(db.String(20), default='draft')
    pay_terms    = db.Column(db.String(200))
    pay_notes    = db.Column(db.String(200))
    tc_standard  = db.Column(db.Text)
    tc_extra     = db.Column(db.Text)
    overall_disc = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)
    created_by   = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    line_items   = db.relationship('LineItem', backref='quote', lazy=True, cascade='all, delete-orphan')

class LineItem(db.Model):
    __tablename__ = 'line_items'
    id            = db.Column(db.Integer, primary_key=True)
    quote_id      = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=False)
    description   = db.Column(db.String(500))
    quantity      = db.Column(db.Float, default=1)
    unit_rate     = db.Column(db.Float, default=0)
    disc_enabled  = db.Column(db.Boolean, default=False)
    disc_pct      = db.Column(db.Float, default=0)
    sort_order    = db.Column(db.Integer, default=0)

class PriceScheduleItem(db.Model):
    __tablename__ = 'price_schedule'
    id            = db.Column(db.Integer, primary_key=True)
    description   = db.Column(db.String(500))
    unit_rate     = db.Column(db.Float, default=0)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

# ── AUTH ──────────────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        data = request.json
        user = User.query.filter_by(email=data.get('email')).first()
        if user and user.check_password(data.get('password')):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            return jsonify({'ok': True}), 200
        return jsonify({'error': 'Invalid email or password'}), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── INITIALIZATION ────────────────────────────────────────────────

@app.route('/api/init', methods=['GET'])
@login_required
def init_db():
    if session.get('user_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    try:
        db.drop_all()
        db.create_all()
        _seed_users()
        return jsonify({'status': 'ok', 'message': 'Database initialised'}), 200
    except Exception as e:
        app.logger.exception("init_db failed")
        return jsonify({'error': str(e)}), 500

def _seed_users():
    users = [
        {'name':'Marilize', 'email':'marilizereinhardt@gmail.com', 'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Shaughn', 'email':'shaughn@simpliwater.com', 'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Christiaan', 'email':'simpliwatermu@gmail.com', 'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Inge', 'email':'inge@simpliwater.com', 'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Tyron', 'email':'tyron@simpliwater.com', 'role':'field','perms':{'dashboard':True,'clients':True,'quotes':True}},
    ]
    for u in users:
        user = User(name=u['name'],email=u['email'],role=u['role'],
                   perm_dashboard=u['perms']['dashboard'],perm_clients=u['perms'].get('clients',True),
                   perm_quotes=u['perms'].get('quotes',True),perm_jobs=True,perm_reports=True,
                   perm_price=u['perms'].get('price',False),perm_users=u['perms'].get('users',False))
        user.set_password('password')
        db.session.add(user)
    db.session.commit()

def _seed_clients():
    pass

# ── CLIENT API ───────────────────────────────────────────────────

@app.route('/api/clients', methods=['GET'])
@login_required
def get_clients():
    clients = Client.query.order_by(Client.name).all()
    return jsonify([{'id':c.id,'name':c.name,'company':c.company,'contact':c.contact,'phone':c.phone,'email':c.email,'vat':c.vat,'brn':c.brn,'addresses':[a.address for a in c.addresses]} for c in clients])

@app.route('/api/clients', methods=['POST'])
@login_required
def create_client():
    data = request.json
    client = Client(name=data.get('name',''),company=data.get('company','') or None,contact=data.get('contact',''),phone=data.get('phone',''),email=data.get('email',''),vat=data.get('vat',''),brn=data.get('brn',''))
    db.session.add(client)
    db.session.flush()
    for addr in data.get('addresses',[]):
        db.session.add(ClientAddress(client_id=client.id,address=addr))
    db.session.commit()
    return jsonify({'id':client.id,'name':client.name}), 201

@app.route('/api/clients/<int:cid>', methods=['DELETE'])
@login_required
def delete_client(cid):
    try:
        client = Client.query.get_or_404(cid)
        if client.quotes:
            return jsonify({'error': f'Cannot delete "{client.name}" — this client has {len(client.quotes)} quote(s). Delete or reassign quotes first.'}), 409
        db.session.delete(client)
        db.session.commit()
        return jsonify({'deleted': cid}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.exception("delete_client failed")
        return jsonify({'error': 'Delete failed'}), 500

@app.route('/api/clients/<int:cid>/addresses', methods=['POST'])
@login_required
def add_address(cid):
    data = request.json
    addr = ClientAddress(client_id=cid,address=data.get('address',''))
    db.session.add(addr)
    db.session.commit()
    return jsonify({'id':addr.id,'address':addr.address}), 201

@app.route('/api/export/clients', methods=['GET'])
@login_required
def export_clients_csv():
    try:
        clients = Client.query.order_by(Client.name).all()
        rows = []
        for c in clients:
            addresses = ' | '.join([a.address for a in c.addresses])
            rows.append({'Client Name': c.name or '', 'Company Name': c.company or '', 'Contact Person': c.contact or '', 'Phone': c.phone or '', 'Email': c.email or '', 'VAT': c.vat or '', 'BRN': c.brn or '', 'Addresses': addresses})
        return jsonify(rows), 200
    except Exception as e:
        app.logger.exception("export_clients_csv failed")
        return jsonify({'error': 'Export failed'}), 500

@app.route('/api/export/quotes', methods=['GET'])
@login_required
def export_quotes_csv():
    try:
        quotes = Quote.query.order_by(Quote.quote_number).all()
        rows = []
        for q in quotes:
            rows.append({'Quote Number': q.quote_number or '', 'Client': q.client.name if q.client else '', 'Job Type': q.job_type or '', 'Date': q.quote_date.strftime('%d/%m/%Y') if q.quote_date else '', 'Amount (MUR)': q.total_amount or 0, 'Status': q.status or '', 'Site Address': q.site_address or '', 'Scope': q.scope or ''})
        return jsonify(rows), 200
    except Exception as e:
        app.logger.exception("export_quotes_csv failed")
        return jsonify({'error': 'Export failed'}), 500

# ── QUOTE API ────────────────────────────────────────────────────

@app.route('/api/quotes', methods=['GET'])
@login_required
def get_quotes():
    try:
        quotes = Quote.query.order_by(Quote.created_at.desc()).all()
        return jsonify([_quote_summary(q) for q in quotes])
    except Exception as e:
        app.logger.exception("get_quotes failed")
        return jsonify({'error': 'Could not load quotes — database error'}), 500

@app.route('/api/quotes/<int:qid>', methods=['GET'])
@login_required
def get_quote(qid):
    q = Quote.query.get_or_404(qid)
    return jsonify(_quote_full(q))

@app.route('/api/quotes', methods=['POST'])
@login_required
def save_quote():
    try:
        data = request.json or {}
        qnum = (data.get('quote_number') or '').strip()
        if not qnum or qnum == 'Select type →':
            return jsonify({'error':'Quote number missing — select a job type first'}), 400
        is_new = not data.get('quote_id')
        if is_new:
            existing = Quote.query.filter_by(quote_number=qnum).first()
            if existing:
                return jsonify({'error':f'Quote number {qnum} already exists. Choose a different number or edit the existing quote.'}), 409
        existing = Quote.query.filter_by(quote_number=qnum).first() if not is_new else None
        q = existing or Quote(quote_number=qnum)
        if not existing:
            db.session.add(q)
        cid = data.get('client_id')
        if cid is not None:
            try:
                cid = int(cid)
                if not Client.query.get(cid):
                    cid = None
            except (TypeError, ValueError):
                cid = None
        q.job_type = data.get('job_type') or None
        q.client_id = cid
        q.site_address = (data.get('site_address') or '')[:500]
        q.scope = data.get('scope') or ''
        q.quote_date = _parse_date(data.get('quote_date')) or date.today()
        q.valid_until = _parse_date(data.get('valid_until'))
        q.status = data.get('status') or 'draft'
        q.pay_terms = (data.get('pay_terms') or '')[:200]
        q.pay_notes = (data.get('pay_notes') or '')[:200]
        q.tc_standard = data.get('tc_standard') or ''
        q.tc_extra = data.get('tc_extra') or ''
        q.overall_disc = float(data.get('overall_disc') or 0)
        q.total_amount = float(data.get('total_amount') or 0)
        q.created_by = session.get('user_id')
        db.session.flush()
        LineItem.query.filter_by(quote_id=q.id).delete()
        for i,item in enumerate(data.get('line_items',[])):
            db.session.add(LineItem(quote_id=q.id,description=(item.get('description') or '')[:500],quantity=float(item.get('quantity') or 1),unit_rate=float(item.get('unit_rate') or 0),disc_enabled=bool(item.get('disc_enabled')),disc_pct=float(item.get('disc_pct') or 0),sort_order=i))
        db.session.commit()
        return jsonify({'id':q.id,'quote_number':q.quote_number}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.exception("save_quote failed")
        if 'column' in str(e).lower():
            return jsonify({'error': 'Save failed — database schema error. Contact support.'}), 500
        return jsonify({'error': 'Save failed — please try again'}), 500

@app.route('/api/quotes/<int:qid>/status', methods=['PATCH'])
@login_required
def update_quote_status(qid):
    try:
        q = Quote.query.get_or_404(qid)
        q.status = request.json.get('status', 'draft')
        db.session.commit()
        return jsonify({'status': q.status}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.exception("update_quote_status failed")
        return jsonify({'error': 'Update failed'}), 500

@app.route('/api/quotes/<int:qid>', methods=['DELETE'])
@login_required
def delete_quote(qid):
    try:
        q = Quote.query.get_or_404(qid)
        db.session.delete(q)
        db.session.commit()
        return jsonify({'deleted': qid}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ── PRICE SCHEDULE API ────────────────────────────────────────────

@app.route('/api/price-schedule', methods=['GET'])
@login_required
def get_price_schedule():
    items = PriceScheduleItem.query.order_by(PriceScheduleItem.description).all()
    return jsonify([{'id':it.id,'description':it.description,'unit_rate':it.unit_rate} for it in items])

@app.route('/api/price-schedule', methods=['POST'])
@login_required
def add_price_item():
    data = request.json
    item = PriceScheduleItem(description=data.get('description',''),unit_rate=float(data.get('unit_rate') or 0))
    db.session.add(item)
    db.session.commit()
    return jsonify({'id':item.id,'description':item.description,'unit_rate':item.unit_rate}), 201

@app.route('/api/price-schedule/<int:iid>', methods=['DELETE'])
@login_required
def delete_price_item(iid):
    try:
        item = PriceScheduleItem.query.get_or_404(iid)
        db.session.delete(item)
        db.session.commit()
        return jsonify({'deleted': iid}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.exception("delete_price_item failed")
        return jsonify({'error': str(e)}), 500

# ── USERS API ────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    if session.get('user_role') != 'admin':
        return jsonify({'error':'Forbidden'}), 403
    users = User.query.filter_by(active=True).all()
    return jsonify([{'id':u.id,'name':u.name,'email':u.email,'role':u.role,'permissions':u.permissions()} for u in users])

@app.route('/api/users/<int:uid>/permissions', methods=['PATCH'])
@login_required
def update_user_permissions(uid):
    if session.get('user_role') != 'admin':
        return jsonify({'error':'Forbidden'}), 403
    user = User.query.get_or_404(uid)
    perms = request.json.get('permissions', {})
    user.perm_dashboard = perms.get('dashboard', True)
    user.perm_clients = perms.get('clients', True)
    user.perm_quotes = perms.get('quotes', True)
    user.perm_jobs = perms.get('jobs', True)
    user.perm_reports = perms.get('reports', True)
    user.perm_price = perms.get('price', False)
    user.perm_users = perms.get('users', False)
    db.session.commit()
    return jsonify(user.permissions()), 200

# ── HELPERS ───────────────────────────────────────────────────────

def _parse_date(d):
    if not d:
        return None
    if isinstance(d, str):
        try:
            return datetime.strptime(d, '%Y-%m-%d').date()
        except:
            return None
    return d

def _quote_summary(q):
    return {
        'id': q.id,
        'quote_number': q.quote_number,
        'job_type': q.job_type,
        'client_name': q.client.name if q.client else '—',
        'quote_date': q.quote_date.strftime('%d/%m/%Y') if q.quote_date else '',
        'status': q.status,
        'total_amount': q.total_amount,
        'locked': q.status in ['accepted', 'rejected']
    }

def _quote_full(q):
    return {
        'id': q.id,
        'quote_number': q.quote_number,
        'job_type': q.job_type,
        'client_id': q.client_id,
        'site_address': q.site_address,
        'scope': q.scope,
        'quote_date': q.quote_date.strftime('%Y-%m-%d') if q.quote_date else '',
        'valid_until': q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '',
        'status': q.status,
        'pay_terms': q.pay_terms,
        'pay_notes': q.pay_notes,
        'tc_standard': q.tc_standard,
        'tc_extra': q.tc_extra,
        'overall_disc': q.overall_disc,
        'total_amount': q.total_amount,
        'line_items': [{'description':li.description,'quantity':li.quantity,'unit_rate':li.unit_rate,'disc_enabled':li.disc_enabled,'disc_pct':li.disc_pct} for li in q.line_items]
    }

# ── MAIN ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session.get('user_id'))
    if not user:
        session.clear()
        return redirect(url_for('login'))
    return render_template('simpliwater_final.html', 
                         user_name=user.name, 
                         user_role=user.role, 
                         user_perms=user.permissions())

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            _seed_users()
        _seed_clients()
    app.run(debug=False)
