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
    # Permissions stored as individual booleans
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
    created_by   = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    line_items   = db.relationship('LineItem', backref='quote', lazy=True, cascade='all, delete-orphan')

class LineItem(db.Model):
    __tablename__ = 'line_items'
    id           = db.Column(db.Integer, primary_key=True)
    quote_id     = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=False)
    description  = db.Column(db.String(500), nullable=False)
    quantity     = db.Column(db.Float, default=1)
    unit_rate    = db.Column(db.Float, default=0)
    disc_enabled = db.Column(db.Boolean, default=False)
    disc_pct     = db.Column(db.Float, default=0)
    sort_order   = db.Column(db.Integer, default=0)

class PriceScheduleItem(db.Model):
    __tablename__ = 'price_schedule'
    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    unit_rate   = db.Column(db.Float, default=0)
    sort_order  = db.Column(db.Integer, default=0)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ── AUTH HELPERS ─────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def send_reset_email(to_email, reset_url):
    if not SENDGRID_API_KEY:
        print(f"[DEV] Reset URL: {reset_url}")
        return True
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject='SimpliWater — Reset your password',
            html_content=f'''
            <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
              <div style="font-size:28px;font-weight:900;color:#0a2540;margin-bottom:4px;">
                Simpli<span style="color:#7ec8e3;">Water</span>
              </div>
              <div style="font-size:11px;color:#6b8aaa;text-transform:uppercase;letter-spacing:1px;margin-bottom:28px;">Internal Portal</div>
              <p style="font-size:15px;color:#0d1f33;margin-bottom:16px;">Hi,</p>
              <p style="font-size:14px;color:#3a5a7a;line-height:1.6;margin-bottom:24px;">
                We received a request to reset your SimpliWater password. Click the button below to set a new password. This link expires in <strong>1 hour</strong>.
              </p>
              <a href="{reset_url}" style="display:inline-block;background:#e8a020;color:#0a2540;padding:13px 28px;border-radius:10px;font-size:14px;font-weight:800;text-decoration:none;letter-spacing:.3px;">
                Reset My Password →
              </a>
              <p style="font-size:12px;color:#6b8aaa;margin-top:24px;line-height:1.6;">
                If you didn't request this, you can safely ignore this email. Your password won't change.
              </p>
              <hr style="border:none;border-top:1px solid #e3f2fd;margin:24px 0;">
              <p style="font-size:11px;color:#6b8aaa;">SimpliWater Ltd · Lot 14, Chemin Vingt Pieds, Pereybere, Mauritius</p>
            </div>
            '''
        )
        sg.send(message)
        return True
    except Exception as e:
        print(f"SendGrid error: {e}")
        return False

# ── AUTH ROUTES ──────────────────────────────────────────────────

@app.route('/login', methods=['GET'])
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    error = request.args.get('error')
    success = request.args.get('success')
    return render_template('login.html', error=error, success=success)

@app.route('/login', methods=['POST'])
def login_post():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = User.query.filter_by(email=email, active=True).first()
    if not user or not user.check_password(password):
        return render_template('login.html', error='Incorrect email or password. Please try again.')
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['user_role'] = user.role
    session['user_perms'] = user.permissions()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/forgot-password', methods=['GET'])
def forgot_password_page():
    return render_template('forgot.html')

@app.route('/forgot-password', methods=['POST'])
def forgot_password_post():
    email = request.form.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()
    # Always show success to prevent email enumeration
    success_msg = "If that email is registered, you'll receive a reset link shortly."
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        reset_url = f"{APP_URL}/reset-password/{token}"
        send_reset_email(user.email, reset_url)
    return render_template('forgot.html', success=success_msg)

@app.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_expires or user.reset_expires < datetime.utcnow():
        return render_template('reset.html', token=token, error='This reset link has expired or is invalid. Please request a new one.')
    return render_template('reset.html', token=token)

@app.route('/reset-password/<token>', methods=['POST'])
def reset_password_post(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_expires or user.reset_expires < datetime.utcnow():
        return render_template('reset.html', token=token, error='This reset link has expired. Please request a new one.')
    password = request.form.get('password', '')
    confirm = request.form.get('confirm', '')
    if len(password) < 8:
        return render_template('reset.html', token=token, error='Password must be at least 8 characters.')
    if password != confirm:
        return render_template('reset.html', token=token, error='Passwords do not match.')
    user.set_password(password)
    user.reset_token = None
    user.reset_expires = None
    db.session.commit()
    return render_template('reset.html', token=token, success='Password updated successfully.')

# ── MAIN APP ROUTE ───────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    user = current_user()
    return render_template('simpliwater_final.html',
        user_name=user.name,
        user_role=user.role,
        user_perms=user.permissions()
    )

# ── SESSION API ──────────────────────────────────────────────────

@app.route('/api/me')
@login_required
def me():
    user = current_user()
    return jsonify({'id':user.id,'name':user.name,'role':user.role,'permissions':user.permissions()})

# ── INIT & SEED ──────────────────────────────────────────────────

@app.route('/api/init', methods=['GET','POST'])
@login_required
def init_db():
    """Initialize database — admin only"""
    if current_user().role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    db.create_all()
    _seed_users()
    _seed_price_schedule()
    _seed_clients()
    return jsonify({'status':'ok','message':'Database initialised'})

def _seed_users():
    if User.query.count() > 0:
        return
    users = [
        {'name':'Shaughn',    'email':'shaughn@simpliwater.mu',          'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Christiaan', 'email':'cmvdh1988@gmail.com',             'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Marilize',   'email':'marilize.reinhardt@gmail.com',    'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Inge',       'email':'inge@simpliwater.mu',             'role':'admin','perms':{'dashboard':True,'price':True,'users':True}},
        {'name':'Tyron',      'email':'tyron@simpliwater.mu',            'role':'field','perms':{'dashboard':False,'price':False,'users':False}},
    ]
    default_password = 'Simpli2026!'
    for u in users:
        user = User(
            name=u['name'], email=u['email'], role=u['role'],
            perm_dashboard=u['perms'].get('dashboard',True),
            perm_clients=True, perm_quotes=True, perm_jobs=True, perm_reports=True,
            perm_price=u['perms'].get('price',False),
            perm_users=u['perms'].get('users',False)
        )
        user.set_password(default_password)
        db.session.add(user)
    db.session.commit()
    print("Users seeded with default password: Simpli2026!")

def _seed_price_schedule():
    if PriceScheduleItem.query.count() > 0:
        return
    items = [
        ('Travel',1500),('Site Establishment (Setup & Cleanup)',3500),('Drain Prep',6850),
        ('CIPP — DN100 Rehabilitation 3mm PVC Felt Drag and Orange Calibration Hose',0),
        ('Consumables',0),('Plant and Equipment on Site',6500),('Labour (Day Rate)',22500),
        ('EBC DN50',2350),('EBC DN75',3200),('EBC DN100',4100),('Labour',22500),
        ('General Plumbing',0),('Post CCTV Inspection and Report',0),('CCTV Inspection',0),
        ('Gas Leak Detection',0),('Radio Detection (Pipe Locating)',0),
        ('CCTV Inspection & Radio Detection (Pipe Locating)',0),('CIPP — DN50 — Brawoliner',0),
        ('Reinstatement of Junction / Ts',0),('Quick Dry Service',0),('Acoustic Leak Detection',0),
        ('Gas Leak Detection (per Hour Rate)',0),('High Pressure & Speed Drain Cleaning',0),
        ('Material',0),('Outsourced Equipment Rental',0),('Overpumping — MH to MH',0),
        ('Water Leak Investigation',0),('Tracer Gas per Hour — Rate',0),
        ('Acoustic Leak Detection per Hour — Rate',0),('Biodyne 301 — Waste Treatment',0),
        ('DN50 Superflex 2mm Felt Liner',0),('Patch Repair — Sectional DN75',0),
        ('Waterproofing',0),('CIPP Patch Repair DN150 (Sectional)',0),('Thermal Image Report and Survey',0),
    ]
    for i,(desc,rate) in enumerate(items):
        db.session.add(PriceScheduleItem(description=desc,unit_rate=rate,sort_order=i))
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
            db.session.add(ClientAddress(client_id=client.id,address=addr))
    db.session.commit()

# ── CLIENT API ───────────────────────────────────────────────────

@app.route('/api/clients', methods=['GET'])
@login_required
def get_clients():
    clients = Client.query.order_by(Client.name).all()
    return jsonify([{'id':c.id,'name':c.name,'contact':c.contact,'phone':c.phone,'email':c.email,'vat':c.vat,'brn':c.brn,'addresses':[a.address for a in c.addresses]} for c in clients])

@app.route('/api/clients', methods=['POST'])
@login_required
def create_client():
    data = request.json
    client = Client(name=data.get('name',''),contact=data.get('contact',''),phone=data.get('phone',''),email=data.get('email',''),vat=data.get('vat',''),brn=data.get('brn',''))
    db.session.add(client)
    db.session.flush()
    for addr in data.get('addresses',[]):
        db.session.add(ClientAddress(client_id=client.id,address=addr))
    db.session.commit()
    return jsonify({'id':client.id,'name':client.name}), 201

@app.route('/api/clients/<int:cid>/addresses', methods=['POST'])
@login_required
def add_address(cid):
    data = request.json
    addr = ClientAddress(client_id=cid,address=data.get('address',''))
    db.session.add(addr)
    db.session.commit()
    return jsonify({'id':addr.id,'address':addr.address}), 201

# ── QUOTE API ────────────────────────────────────────────────────

@app.route('/api/quotes', methods=['GET'])
@login_required
def get_quotes():
    try:
        quotes = Quote.query.order_by(Quote.created_at.desc()).all()
        return jsonify([_quote_summary(q) for q in quotes])
    except Exception as e:
        app.logger.exception("get_quotes failed")
        # Don't expose database schema in error messages
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
        existing = Quote.query.filter_by(quote_number=qnum).first()
        q = existing or Quote(quote_number=qnum)
        if not existing:
            db.session.add(q)
        # Validate client_id - must exist or be None
        cid = data.get('client_id')
        if cid is not None:
            try:
                cid = int(cid)
                if not Client.query.get(cid):
                    cid = None
            except (TypeError, ValueError):
                cid = None
        q.job_type    = data.get('job_type') or None
        q.client_id   = cid
        q.site_address= (data.get('site_address') or '')[:500]
        q.scope       = data.get('scope') or ''
        q.quote_date  = _parse_date(data.get('quote_date')) or date.today()
        q.valid_until = _parse_date(data.get('valid_until'))
        q.status      = data.get('status') or 'draft'
        q.pay_terms   = (data.get('pay_terms') or '')[:200]
        q.pay_notes   = (data.get('pay_notes') or '')[:200]
        q.tc_standard = data.get('tc_standard') or ''
        q.tc_extra    = data.get('tc_extra') or ''
        q.overall_disc= float(data.get('overall_disc') or 0)
        q.total_amount= float(data.get('total_amount') or 0)
        q.created_by  = session.get('user_id')
        db.session.flush()
        LineItem.query.filter_by(quote_id=q.id).delete()
        for i,item in enumerate(data.get('line_items',[])):
            db.session.add(LineItem(
                quote_id=q.id,
                description=(item.get('description') or '')[:500],
                quantity=float(item.get('quantity') or 1),
                unit_rate=float(item.get('unit_rate') or 0),
                disc_enabled=bool(item.get('disc_enabled')),
                disc_pct=float(item.get('disc_pct') or 0),
                sort_order=i
            ))
        db.session.commit()
        return jsonify({'id':q.id,'quote_number':q.quote_number}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.exception("save_quote failed")
        # Log the real error but return generic message to prevent schema disclosure
        if 'column' in str(e).lower() or 'undefined' in str(e).lower():
            return jsonify({'error': 'Save failed — database schema error. Please contact support.'}), 500
        return jsonify({'error': 'Save failed — please try again or contact support'}), 500

@app.route('/api/quotes/<int:qid>/status', methods=['PATCH'])
@login_required
def update_status(qid):
    q = Quote.query.get_or_404(qid)
    if q.status in ('accepted','rejected'):
        return jsonify({'error':'Locked'}), 403
    q.status = request.json.get('status',q.status)
    db.session.commit()
    return jsonify({'status':q.status})

# ── PRICE SCHEDULE API ───────────────────────────────────────────

@app.route('/api/price-schedule', methods=['GET'])
@login_required
def get_price_schedule():
    items = PriceScheduleItem.query.order_by(PriceScheduleItem.sort_order).all()
    return jsonify([{'id':i.id,'description':i.description,'unit_rate':i.unit_rate} for i in items])

@app.route('/api/price-schedule/<int:iid>', methods=['PATCH'])
@login_required
def update_price(iid):
    item = PriceScheduleItem.query.get_or_404(iid)
    item.unit_rate=request.json.get('unit_rate',item.unit_rate)
    item.updated_at=datetime.utcnow()
    db.session.commit()
    return jsonify({'id':item.id,'unit_rate':item.unit_rate})

@app.route('/api/price-schedule', methods=['POST'])
@login_required
def add_price_item():
    data = request.json
    item = PriceScheduleItem(description=data.get('description',''),unit_rate=data.get('unit_rate',0),sort_order=PriceScheduleItem.query.count())
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
def update_permissions(uid):
    if session.get('user_role') != 'admin':
        return jsonify({'error':'Forbidden'}), 403
    user = User.query.get_or_404(uid)
    data = request.json
    perm_map = {'dashboard':'perm_dashboard','clients':'perm_clients','quotes':'perm_quotes','jobs':'perm_jobs','reports':'perm_reports','price':'perm_price','users':'perm_users'}
    for key,attr in perm_map.items():
        if key in data:
            setattr(user,attr,data[key])
    db.session.commit()
    return jsonify({'permissions':user.permissions()})

# ── HELPERS ──────────────────────────────────────────────────────

def _parse_date(d):
    if not d: return None
    try: return datetime.strptime(d,'%Y-%m-%d').date()
    except: return None

def _quote_summary(q):
    return {
        'id': q.id,
        'quote_number': q.quote_number or '',
        'job_type': q.job_type or '',
        'client_name': q.client.name if q.client else '',
        'quote_date': q.quote_date.strftime('%d/%m/%Y') if q.quote_date else '',
        'status': q.status or 'draft',
        'total_amount': q.total_amount or 0,
        'locked': (q.status or '') in ('accepted','rejected')
    }

def _quote_full(q):
    s=_quote_summary(q)
    s.update({'client_id':q.client_id,'site_address':q.site_address,'scope':q.scope,'valid_until':q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '','quote_date_raw':q.quote_date.strftime('%Y-%m-%d') if q.quote_date else '','pay_terms':q.pay_terms,'pay_notes':q.pay_notes,'tc_standard':q.tc_standard,'tc_extra':q.tc_extra,'overall_disc':q.overall_disc,'line_items':[{'description':li.description,'quantity':li.quantity,'unit_rate':li.unit_rate,'disc_enabled':li.disc_enabled,'disc_pct':li.disc_pct} for li in q.line_items]})
    return s

if __name__ == '__main__':
    app.run(debug=True)
