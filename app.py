import os, re, json, hmac, hashlib, base64, requests
  from datetime import datetime
  from functools import wraps
  from dotenv import load_dotenv
  load_dotenv()

  from flask import (Flask, render_template, request, session, redirect,
                     url_for, jsonify, flash, abort, current_app)
  from flask_wtf.csrf import CSRFProtect
  from flask_limiter import Limiter
  from flask_limiter.util import get_remote_address
  from flask_mail import Mail, Message
  from google.cloud.firestore_v1 import SERVER_TIMESTAMP
  import pytz
  import razorpay
  import openai

  from firebase_config import get_db, get_auth, init_firebase

  app = Flask(__name__)
  app.secret_key = os.environ.get('SECRET_KEY', 'dev-change-me')
  app.config['WTF_CSRF_ENABLED'] = True
  app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 7
  app.config['SESSION_COOKIE_HTTPONLY'] = True
  app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

  # Firebase Web config (frontend)
  FIREBASE_WEB = {
      'apiKey': os.environ.get('FIREBASE_API_KEY', 'AIzaSyD3ML9k7RSbeoVze0su8PoE69llfgeqr1k'),
      'authDomain': os.environ.get('FIREBASE_AUTH_DOMAIN', 'codeforge-d3aa2.firebaseapp.com'),
      'projectId': os.environ.get('FIREBASE_PROJECT_ID', 'codeforge-d3aa2'),
      'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', 'codeforge-d3aa2.firebasestorage.app'),
      'messagingSenderId': os.environ.get('FIREBASE_MESSAGING_SENDER_ID', '907268826856'),
      'appId': os.environ.get('FIREBASE_APP_ID', '1:907268826856:web:aedb8eb1c674bad9ab4b5d'),
  }

  # Mail config
  app.config.update(
      MAIL_SERVER='smtp.gmail.com',
      MAIL_PORT=587,
      MAIL_USE_TLS=True,
      MAIL_USERNAME=os.environ.get('MAIL_USERNAME', ''),
      MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', ''),
      MAIL_DEFAULT_SENDER=os.environ.get('MAIL_USERNAME', ''),
  )

  csrf = CSRFProtect(app)
  limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["300/day", "60/hour"])
  mail = Mail(app)

  with app.app_context():
      try:
          init_firebase()
      except Exception as e:
          print(f"Firebase init warning: {e}")

  # ─── Helpers ────────────────────────────────────────────────────────────────

  CATEGORIES = [
      'Discord Bots', 'Websites', 'Web Applications', 'Source Codes',
      'APIs', 'SaaS Products', 'Templates', 'Digital Downloads', 'Custom Development Services'
  ]

  def current_user():
      uid = session.get('uid')
      if not uid:
          return None
      try:
          doc = get_db().collection('users').document(uid).get()
          if doc.exists:
              d = doc.to_dict()
              d['uid'] = uid
              return d
      except Exception:
          pass
      return None

  def login_required(f):
      @wraps(f)
      def wrap(*a, **kw):
          if not session.get('uid'):
              return redirect(url_for('login', next=request.url))
          return f(*a, **kw)
      return wrap

  def admin_required(f):
      @wraps(f)
      def wrap(*a, **kw):
          if not session.get('is_admin'):
              abort(403)
          return f(*a, **kw)
      return wrap

  def super_admin_required(f):
      @wraps(f)
      def wrap(*a, **kw):
          if 'super_admin' not in session.get('admin_permissions', []):
              abort(403)
          return f(*a, **kw)
      return wrap

  def can(permission):
      perms = session.get('admin_permissions', [])
      return 'super_admin' in perms or permission in perms

  def notify(uid, title, msg, kind='info'):
      try:
          get_db().collection('notifications').add({
              'uid': uid, 'title': title, 'message': msg,
              'type': kind, 'read': False, 'timestamp': SERVER_TIMESTAMP
          })
      except Exception:
          pass

  def log_admin(action, details=None):
      try:
          get_db().collection('admin_logs').add({
              'admin_uid': session.get('uid', ''),
              'admin_email': session.get('email', ''),
              'action': action, 'details': details or {},
              'timestamp': SERVER_TIMESTAMP
          })
      except Exception:
          pass

  def slugify(s):
      return re.sub(r'[^a-z0-9-]', '', s.lower().replace(' ', '-'))

  def send_mail_safe(to, subject, body):
      try:
          m = Message(subject, recipients=[to], body=body)
          mail.send(m)
      except Exception as e:
          print(f"Mail error: {e}")

  # ─── Context processor ───────────────────────────────────────────────────────

  @app.context_processor
  def inject_globals():
      return {
          'firebase': FIREBASE_WEB,
          'current_user': current_user(),
          'session': session,
      }

  # ─── Error handlers ──────────────────────────────────────────────────────────

  @app.errorhandler(404)
  def e404(e): return render_template('404.html'), 404

  @app.errorhandler(403)
  def e403(e): return render_template('403.html'), 403

  @app.errorhandler(500)
  def e500(e): return render_template('500.html'), 500

  # ═══════════════════════════════════════════════════════════════
  # AUTH
  # ═══════════════════════════════════════════════════════════════

  @app.route('/login')
  def login():
      if session.get('uid'):
          return redirect(url_for('dashboard'))
      return render_template('login.html')

  @app.route('/register')
  def register():
      if session.get('uid'):
          return redirect(url_for('dashboard'))
      return render_template('register.html')

  @app.route('/auth/session', methods=['POST'])
  @csrf.exempt
  def session_login():
      try:
          id_token = request.json.get('idToken')
          fa = get_auth()
          decoded = fa.verify_id_token(id_token)
          uid = decoded['uid']
          email = decoded.get('email', '')
          name = decoded.get('name', email.split('@')[0] if email else 'User')
          photo = decoded.get('picture', '')
          db = get_db()
          user_ref = db.collection('users').document(uid)
          if not user_ref.get().exists:
              user_ref.set({
                  'uid': uid, 'email': email, 'name': name, 'photo': photo,
                  'wishlist': [], 'created_at': SERVER_TIMESTAMP,
                  'email_verified': decoded.get('email_verified', False)
              })
          user_data = user_ref.get().to_dict() or {}
          session.permanent = True
          session['uid'] = uid
          session['email'] = email
          session['name'] = name
          session['photo'] = photo

          # Check admin
          super_email = os.environ.get('SUPER_ADMIN_EMAIL', '')
          admin_doc = db.collection('admins').document(uid).get()
          if email == super_email:
              session['is_admin'] = True
              session['admin_role'] = 'super_admin'
              session['admin_permissions'] = ['super_admin']
          elif admin_doc.exists:
              ad = admin_doc.to_dict()
              session['is_admin'] = True
              session['admin_role'] = ad.get('role', 'admin')
              session['admin_permissions'] = ad.get('permissions', [])
          else:
              session['is_admin'] = False
              session['admin_role'] = ''
              session['admin_permissions'] = []

          return jsonify({'ok': True, 'is_admin': session.get('is_admin', False)})
      except Exception as e:
          return jsonify({'ok': False, 'error': str(e)}), 400

  @app.route('/logout')
  def logout():
      session.clear()
      return redirect(url_for('index'))

  # ═══════════════════════════════════════════════════════════════
  # MAIN PAGES
  # ═══════════════════════════════════════════════════════════════

  @app.route('/')
  def index():
      db = get_db()
      try:
          featured = [{'id': p.id, **p.to_dict()}
                      for p in db.collection('products')
                      .where('featured', '==', True).where('active', '==', True).limit(8).stream()]
          trending = [{'id': p.id, **p.to_dict()}
                      for p in db.collection('products')
                      .where('active', '==', True)
                      .order_by('sales_count', direction='DESCENDING').limit(8).stream()]
          cats = [{'id': c.id, **c.to_dict()}
                  for c in db.collection('categories').where('active', '==', True).stream()]
      except Exception:
          featured, trending, cats = [], [], []
      return render_template('index.html', featured=featured, trending=trending, categories=cats)

  # ═══════════════════════════════════════════════════════════════
  # MARKETPLACE
  # ═══════════════════════════════════════════════════════════════

  @app.route('/marketplace')
  def marketplace():
      db = get_db()
      cat = request.args.get('cat', '')
      tag = request.args.get('tag', '')
      q = request.args.get('q', '')
      sort = request.args.get('sort', 'newest')
      page = max(1, int(request.args.get('page', 1)))
      per = 12

      query = db.collection('products').where('active', '==', True)
      if cat:
          query = query.where('category', '==', cat)

      order_map = {
          'price_asc': ('price', 'ASCENDING'),
          'price_desc': ('price', 'DESCENDING'),
          'popular': ('sales_count', 'DESCENDING'),
          'newest': ('created_at', 'DESCENDING'),
      }
      field, direction = order_map.get(sort, ('created_at', 'DESCENDING'))
      query = query.order_by(field, direction=direction)

      all_prods = [{'id': p.id, **p.to_dict()} for p in query.stream()]

      if q:
          ql = q.lower()
          all_prods = [p for p in all_prods
                       if ql in p.get('name','').lower() or ql in p.get('short_description','').lower()]
      if tag:
          all_prods = [p for p in all_prods if tag in p.get('tags', [])]

      total = len(all_prods)
      prods = all_prods[(page-1)*per : page*per]
      total_pages = max(1, (total + per - 1) // per)

      return render_template('marketplace.html',
          products=prods, total=total, page=page, total_pages=total_pages,
          CATEGORIES=CATEGORIES, cat=cat, tag=tag, q=q, sort=sort)

  @app.route('/product/<slug>')
  def product(slug):
      db = get_db()
      docs = list(db.collection('products').where('slug','==',slug).where('active','==',True).limit(1).stream())
      if not docs:
          abort(404)
      p = docs[0]
      prod = {'id': p.id, **p.to_dict()}
      p.reference.update({'view_count': prod.get('view_count', 0) + 1})

      reviews = [{'id': r.id, **r.to_dict()}
                 for r in db.collection('reviews').where('product_id','==',p.id)
                 .order_by('created_at', direction='DESCENDING').limit(20).stream()]

      related = [{'id': r.id, **r.to_dict()}
                 for r in db.collection('products')
                 .where('category','==',prod.get('category',''))
                 .where('active','==',True).limit(4).stream()
                 if r.id != p.id][:3]

      purchased = False
      uid = session.get('uid')
      if uid:
          purchased = bool(list(db.collection('orders')
              .where('uid','==',uid).where('product_id','==',p.id)
              .where('status','==','completed').limit(1).stream()))

      return render_template('product.html',
          product=prod, reviews=reviews, related=related,
          purchased=purchased,
          rz_key=os.environ.get('RAZORPAY_KEY_ID', ''))

  @app.route('/product/<product_id>/review', methods=['POST'])
  @login_required
  def add_review(product_id):
      uid = session['uid']
      db = get_db()
      purchased = bool(list(db.collection('orders')
          .where('uid','==',uid).where('product_id','==',product_id)
          .where('status','==','completed').limit(1).stream()))
      if not purchased:
          flash('You must purchase this product to leave a review.', 'error')
          return redirect(request.referrer or url_for('marketplace'))
      rating = min(5, max(1, int(request.form.get('rating', 5))))
      comment = request.form.get('comment', '').strip()[:1000]
      db.collection('reviews').add({
          'product_id': product_id, 'uid': uid,
          'name': session.get('name', 'User'), 'rating': rating,
          'comment': comment, 'created_at': SERVER_TIMESTAMP
      })
      all_reviews = list(db.collection('reviews').where('product_id','==',product_id).stream())
      avg = sum(r.to_dict().get('rating', 0) for r in all_reviews) / max(len(all_reviews), 1)
      db.collection('products').document(product_id).update({
          'avg_rating': round(avg, 1), 'review_count': len(all_reviews)
      })
      flash('Review submitted. Thank you!', 'success')
      return redirect(request.referrer or url_for('marketplace'))

  # ═══════════════════════════════════════════════════════════════
  # USER ACCOUNT
  # ═══════════════════════════════════════════════════════════════

  @app.route('/dashboard')
  @login_required
  def dashboard():
      uid = session['uid']
      db = get_db()
      orders = [{'id': o.id, **o.to_dict()}
                for o in db.collection('orders').where('uid','==',uid)
                .order_by('created_at', direction='DESCENDING').limit(10).stream()]
      notifs = [{'id': n.id, **n.to_dict()}
                for n in db.collection('notifications').where('uid','==',uid)
                .where('read','==',False).limit(5).stream()]
      return render_template('dashboard.html', orders=orders, notifications=notifs)

  @app.route('/profile', methods=['GET','POST'])
  @login_required
  def profile():
      uid = session['uid']
      db = get_db()
      if request.method == 'POST':
          name = request.form.get('name','').strip()[:80]
          bio = request.form.get('bio','').strip()[:300]
          db.collection('users').document(uid).update({'name': name, 'bio': bio})
          session['name'] = name
          flash('Profile updated.', 'success')
          return redirect(url_for('profile'))
      return render_template('profile.html')

  @app.route('/wishlist')
  @login_required
  def wishlist():
      db = get_db()
      u = current_user() or {}
      ids = u.get('wishlist', [])[:20]
      prods = []
      for pid in ids:
          doc = db.collection('products').document(pid).get()
          if doc.exists:
              prods.append({'id': doc.id, **doc.to_dict()})
      return render_template('wishlist.html', products=prods)

  @app.route('/wishlist/toggle', methods=['POST'])
  @login_required
  @csrf.exempt
  def wishlist_toggle():
      uid = session['uid']
      pid = request.json.get('product_id')
      db = get_db()
      ref = db.collection('users').document(uid)
      u = ref.get().to_dict() or {}
      wl = u.get('wishlist', [])
      if pid in wl:
          wl.remove(pid)
          added = False
      else:
          wl.append(pid)
          added = True
      ref.update({'wishlist': wl})
      return jsonify({'added': added})

  @app.route('/orders')
  @login_required
  def my_orders():
      uid = session['uid']
      db = get_db()
      orders = [{'id': o.id, **o.to_dict()}
                for o in db.collection('orders').where('uid','==',uid)
                .order_by('created_at', direction='DESCENDING').stream()]
      return render_template('orders.html', orders=orders)

  @app.route('/orders/<order_id>/download')
  @login_required
  def download(order_id):
      uid = session['uid']
      db = get_db()
      o = db.collection('orders').document(order_id).get()
      if not o.exists:
          abort(404)
      od = o.to_dict()
      if od.get('uid') != uid or od.get('status') != 'completed':
          abort(403)
      p = db.collection('products').document(od['product_id']).get()
      if not p.exists:
          abort(404)
      link = p.to_dict().get('download_link', '')
      if not link:
          flash('Download link not available yet. Contact support.', 'error')
          return redirect(url_for('my_orders'))
      db.collection('download_logs').add({
          'uid': uid, 'order_id': order_id,
          'product_id': od['product_id'], 'timestamp': SERVER_TIMESTAMP
      })
      return redirect(link)

  @app.route('/notifications')
  @login_required
  def notifications():
      uid = session['uid']
      db = get_db()
      notifs = [{'id': n.id, **n.to_dict()}
                for n in db.collection('notifications').where('uid','==',uid)
                .order_by('timestamp', direction='DESCENDING').limit(50).stream()]
      for n in db.collection('notifications').where('uid','==',uid).where('read','==',False).stream():
          n.reference.update({'read': True})
      return render_template('notifications.html', notifications=notifs)

  # ═══════════════════════════════════════════════════════════════
  # ORDERS / PAYMENTS
  # ═══════════════════════════════════════════════════════════════

  @app.route('/order/create', methods=['POST'])
  @login_required
  @csrf.exempt
  def order_create():
      uid = session['uid']
      data = request.json
      pid = data.get('product_id')
      coupon = data.get('coupon', '').upper()
      db = get_db()
      p = db.collection('products').document(pid).get()
      if not p.exists:
          return jsonify({'error': 'Product not found'}), 404
      pd = p.to_dict()
      price = float(pd.get('discount_price') or pd.get('price', 0))
      discount = 0

      if coupon:
          cdocs = list(db.collection('coupons').where('code','==',coupon)
                       .where('active','==',True).limit(1).stream())
          if cdocs:
              cd = cdocs[0].to_dict()
              if cd.get('usage_count', 0) < cd.get('usage_limit', 9999):
                  if cd.get('type') == 'percentage':
                      discount = price * cd['value'] / 100
                  else:
                      discount = float(cd['value'])
                  price = max(0, price - discount)

      if price == 0:
          ref = db.collection('orders').add({
              'uid': uid, 'product_id': pid,
              'product_name': pd.get('name'), 'slug': pd.get('slug'),
              'amount': 0, 'status': 'completed', 'payment_method': 'free',
              'coupon': coupon, 'discount': discount,
              'created_at': SERVER_TIMESTAMP
          })
          db.collection('products').document(pid).update({'sales_count': pd.get('sales_count', 0) + 1})
          notify(uid, 'Order Confirmed', f'{pd["name"]} is now available in your orders.', 'success')
          return jsonify({'status': 'free', 'order_id': ref[1].id})

      rz = razorpay.Client(auth=(os.environ.get('RAZORPAY_KEY_ID',''), os.environ.get('RAZORPAY_KEY_SECRET','')))
      rz_order = rz.order.create({
          'amount': int(price * 100), 'currency': 'INR',
          'receipt': f'cf_{uid[:6]}_{pid[:6]}',
          'notes': {'uid': uid, 'product_id': pid}
      })
      db.collection('orders').add({
          'uid': uid, 'product_id': pid,
          'product_name': pd.get('name'), 'slug': pd.get('slug'),
          'amount': price, 'status': 'pending',
          'razorpay_order_id': rz_order['id'],
          'coupon': coupon, 'discount': discount,
          'created_at': SERVER_TIMESTAMP
      })
      return jsonify({
          'status': 'pay', 'rz_order_id': rz_order['id'],
          'amount': int(price * 100), 'key': os.environ.get('RAZORPAY_KEY_ID','')
      })

  @app.route('/order/verify', methods=['POST'])
  @login_required
  @csrf.exempt
  def order_verify():
      uid = session['uid']
      d = request.json
      secret = os.environ.get('RAZORPAY_KEY_SECRET', '').encode()
      expected = hmac.new(secret, f"{d['razorpay_order_id']}|{d['razorpay_payment_id']}".encode(), hashlib.sha256).hexdigest()
      if expected != d.get('razorpay_signature'):
          return jsonify({'error': 'Invalid signature'}), 400
      db = get_db()
      ords = list(db.collection('orders').where('razorpay_order_id','==',d['razorpay_order_id']).where('uid','==',uid).limit(1).stream())
      if not ords:
          return jsonify({'error': 'Order not found'}), 404
      o = ords[0]
      od = o.to_dict()
      o.reference.update({'status': 'completed', 'razorpay_payment_id': d['razorpay_payment_id']})
      pp = db.collection('products').document(od['product_id']).get()
      if pp.exists:
          pdata = pp.to_dict()
          pp.reference.update({'sales_count': pdata.get('sales_count',0) + 1})
      notify(uid, 'Payment Successful', f'You can now download {od.get("product_name","")} from your orders.', 'success')
      return jsonify({'status': 'ok'})

  @app.route('/coupon/check', methods=['POST'])
  @csrf.exempt
  def coupon_check():
      code = request.json.get('code', '').upper()
      pid = request.json.get('product_id')
      db = get_db()
      docs = list(db.collection('coupons').where('code','==',code).where('active','==',True).limit(1).stream())
      if not docs:
          return jsonify({'valid': False, 'msg': 'Invalid or expired coupon.'})
      cd = docs[0].to_dict()
      p = db.collection('products').document(pid).get()
      if not p.exists:
          return jsonify({'valid': False, 'msg': 'Product not found.'})
      price = float(p.to_dict().get('discount_price') or p.to_dict().get('price', 0))
      if cd.get('type') == 'percentage':
          disc = price * cd['value'] / 100
      else:
          disc = float(cd['value'])
      final = max(0, price - disc)
      return jsonify({'valid': True, 'discount': round(disc, 2), 'final': round(final, 2), 'msg': f'Coupon applied! You save ₹{disc:.0f}'})

  # ═══════════════════════════════════════════════════════════════
  # CUSTOM ORDER
  # ═══════════════════════════════════════════════════════════════

  @app.route('/custom-order', methods=['GET','POST'])
  @login_required
  def custom_order():
      if request.method == 'POST':
          uid = session['uid']
          db = get_db()
          db.collection('custom_orders').add({
              'uid': uid, 'name': session.get('name'),
              'email': session.get('email'),
              'title': request.form.get('title'),
              'description': request.form.get('description'),
              'features': request.form.get('features'),
              'budget': request.form.get('budget'),
              'timeline': request.form.get('timeline'),
              'reference_urls': request.form.get('reference_urls'),
              'notes': request.form.get('notes'),
              'status': 'pending', 'created_at': SERVER_TIMESTAMP
          })
          admin_email = os.environ.get('SUPER_ADMIN_EMAIL','')
          if admin_email:
              send_mail_safe(admin_email,
                  f'New Custom Order: {request.form.get("title")}',
                  f'From: {session.get("name")} ({session.get("email")})
Budget: {request.form.get("budget")}
Timeline: {request.form.get("timeline")}

{request.form.get("description")}')
          notify(uid, 'Custom Order Received', 'We received your custom order and will respond within 24 hours.', 'info')
          flash('Custom order submitted! We will contact you shortly.', 'success')
          return redirect(url_for('dashboard'))
      return render_template('custom_order.html')

  # ═══════════════════════════════════════════════════════════════
  # AI CHAT
  # ═══════════════════════════════════════════════════════════════

  @app.route('/ai')
  def ai_chat():
      db = get_db()
      doc = db.collection('settings').document('ai').get()
      ai_cfg = doc.to_dict() if doc.exists else {}
      if not ai_cfg.get('enabled', True):
          abort(404)
      return render_template('ai_chat.html', ai=ai_cfg)

  @app.route('/ai/chat', methods=['POST'])
  @csrf.exempt
  def ai_chat_api():
      db = get_db()
      doc = db.collection('settings').document('ai').get()
      cfg = doc.to_dict() if doc.exists else {}
      if not cfg.get('enabled', True):
          return jsonify({'reply': 'AI is currently disabled.'}), 403

      msg = request.json.get('message', '').strip()
      history = request.json.get('history', [])[-10:]
      if not msg:
          return jsonify({'reply': 'Please send a message.'})

      api_key = os.environ.get('OPENAI_API_KEY', '')
      if not api_key:
          return jsonify({'reply': 'AI service is not configured yet. Please contact support.'})

      products = [{'name': p.to_dict().get('name'), 'category': p.to_dict().get('category'),
                   'price': p.to_dict().get('price'), 'discount_price': p.to_dict().get('discount_price'),
                   'short_description': p.to_dict().get('short_description'),
                   'slug': p.to_dict().get('slug'),
                   'features': p.to_dict().get('features', [])[:5]}
                  for p in db.collection('products').where('active','==',True).limit(40).stream()]

      system = cfg.get('system_prompt', 'You are CodeForge AI, a helpful assistant for a digital product marketplace.')
      system += f"

Available products:
{json.dumps(products, indent=2)}"
      system += "

Always reply in the same language the user uses. Share product links as: /product/[slug]. Do not read URLs aloud."

      messages = [{'role':'system','content':system}]
      for h in history:
          messages.append({'role': h['role'], 'content': h['content']})
      messages.append({'role':'user','content':msg})

      try:
          client = openai.OpenAI(api_key=api_key)
          resp = client.chat.completions.create(
              model=cfg.get('model','gpt-3.5-turbo'),
              messages=messages, max_tokens=700, temperature=0.7
          )
          reply = resp.choices[0].message.content
          uid = session.get('uid', 'anon')
          db.collection('ai_conversations').add({
              'uid': uid, 'message': msg,
              'reply': reply[:500], 'timestamp': SERVER_TIMESTAMP
          })
          return jsonify({'reply': reply})
      except Exception as e:
          return jsonify({'reply': 'Sorry, I am having trouble right now. Please try again.'})

  # ═══════════════════════════════════════════════════════════════
  # LEGAL PAGES
  # ═══════════════════════════════════════════════════════════════

  def legal_page(slug, title):
      db = get_db()
      doc = db.collection('legal_pages').document(slug).get()
      content = doc.to_dict().get('content', '') if doc.exists else ''
      return render_template('legal.html', title=title, content=content)

  @app.route('/privacy-policy')
  def privacy(): return legal_page('privacy-policy', 'Privacy Policy')

  @app.route('/terms-of-service')
  def terms(): return legal_page('terms-of-service', 'Terms of Service')

  @app.route('/refund-policy')
  def refund(): return legal_page('refund-policy', 'Refund Policy')

  @app.route('/cookie-policy')
  def cookies(): return legal_page('cookie-policy', 'Cookie Policy')

  @app.route('/disclaimer')
  def disclaimer(): return legal_page('disclaimer', 'Disclaimer')

  @app.route('/about-us')
  def about(): return legal_page('about-us', 'About Us')

  @app.route('/contact-us', methods=['GET','POST'])
  def contact():
      if request.method == 'POST':
          db = get_db()
          db.collection('contact_messages').add({
              'name': request.form.get('name'),
              'email': request.form.get('email'),
              'subject': request.form.get('subject'),
              'message': request.form.get('message'),
              'timestamp': SERVER_TIMESTAMP
          })
          flash('Message sent! We will reply within 24 hours.', 'success')
          return redirect(url_for('contact'))
      return render_template('contact.html')

  # ═══════════════════════════════════════════════════════════════
  # ADMIN PANEL
  # ═══════════════════════════════════════════════════════════════

  @app.route('/admin')
  @admin_required
  def admin_dashboard():
      db = get_db()
      try:
          orders_done = list(db.collection('orders').where('status','==','completed').stream())
          revenue = sum(float(o.to_dict().get('amount', 0)) for o in orders_done)
          products_count = len(list(db.collection('products').stream()))
          users_count = len(list(db.collection('users').stream()))
          pending_custom = len(list(db.collection('custom_orders').where('status','==','pending').stream()))
          recent = [{'id':o.id,**o.to_dict()}
                    for o in db.collection('orders').order_by('created_at', direction='DESCENDING').limit(8).stream()]
          stats = {'revenue': revenue, 'orders': len(orders_done), 'products': products_count,
                   'users': users_count, 'pending_custom': pending_custom}
      except Exception as e:
          stats = {'revenue':0,'orders':0,'products':0,'users':0,'pending_custom':0}
          recent = []
      return render_template('admin/dashboard.html', stats=stats, recent=recent)

  @app.route('/admin/products')
  @admin_required
  def admin_products():
      if not can('manage_products'): abort(403)
      prods = [{'id':p.id,**p.to_dict()}
               for p in get_db().collection('products').order_by('created_at', direction='DESCENDING').stream()]
      return render_template('admin/products.html', products=prods)

  @app.route('/admin/products/new', methods=['GET','POST'])
  @admin_required
  def admin_product_new():
      if not can('manage_products'): abort(403)
      if request.method == 'POST':
          f = request.form
          db = get_db()
          data = {
              'name': f.get('name'), 'slug': slugify(f.get('name','')),
              'short_description': f.get('short_description'),
              'full_description': f.get('full_description'),
              'features': [x.strip() for x in f.get('features','').splitlines() if x.strip()],
              'category': f.get('category'), 'tags': [t.strip() for t in f.get('tags','').split(',') if t.strip()],
              'price': float(f.get('price', 0)),
              'discount_price': float(f.get('discount_price')) if f.get('discount_price') else None,
              'thumbnail': f.get('thumbnail'), 'banner': f.get('banner'),
              'gallery': [x.strip() for x in f.get('gallery','').splitlines() if x.strip()],
              'demo_link': f.get('demo_link'), 'documentation': f.get('documentation'),
              'download_link': f.get('download_link'), 'version': f.get('version'),
              'changelog': f.get('changelog'), 'seo_title': f.get('seo_title'),
              'seo_description': f.get('seo_description'),
              'active': 'active' in request.form, 'featured': 'featured' in request.form,
              'sales_count': 0, 'view_count': 0, 'avg_rating': 0, 'review_count': 0,
              'created_at': SERVER_TIMESTAMP
          }
          db.collection('products').add(data)
          log_admin('create_product', {'name': data['name']})
          flash('Product created.', 'success')
          return redirect(url_for('admin_products'))
      return render_template('admin/product_form.html', product=None, CATEGORIES=CATEGORIES)

  @app.route('/admin/products/<pid>/edit', methods=['GET','POST'])
  @admin_required
  def admin_product_edit(pid):
      if not can('manage_products'): abort(403)
      db = get_db()
      ref = db.collection('products').document(pid)
      p = ref.get()
      if not p.exists: abort(404)
      prod = {'id': p.id, **p.to_dict()}
      if request.method == 'POST':
          f = request.form
          ref.update({
              'name': f.get('name'), 'slug': slugify(f.get('name','')),
              'short_description': f.get('short_description'),
              'full_description': f.get('full_description'),
              'features': [x.strip() for x in f.get('features','').splitlines() if x.strip()],
              'category': f.get('category'),
              'tags': [t.strip() for t in f.get('tags','').split(',') if t.strip()],
              'price': float(f.get('price', 0)),
              'discount_price': float(f.get('discount_price')) if f.get('discount_price') else None,
              'thumbnail': f.get('thumbnail'), 'banner': f.get('banner'),
              'gallery': [x.strip() for x in f.get('gallery','').splitlines() if x.strip()],
              'demo_link': f.get('demo_link'), 'documentation': f.get('documentation'),
              'download_link': f.get('download_link'), 'version': f.get('version'),
              'changelog': f.get('changelog'), 'seo_title': f.get('seo_title'),
              'seo_description': f.get('seo_description'),
              'active': 'active' in request.form, 'featured': 'featured' in request.form,
              'updated_at': SERVER_TIMESTAMP
          })
          log_admin('edit_product', {'pid': pid})
          flash('Product updated.', 'success')
          return redirect(url_for('admin_products'))
      return render_template('admin/product_form.html', product=prod, CATEGORIES=CATEGORIES)

  @app.route('/admin/products/<pid>/delete', methods=['POST'])
  @admin_required
  def admin_product_delete(pid):
      if not can('manage_products'): abort(403)
      get_db().collection('products').document(pid).delete()
      log_admin('delete_product', {'pid': pid})
      flash('Product deleted.', 'success')
      return redirect(url_for('admin_products'))

  @app.route('/admin/orders')
  @admin_required
  def admin_orders():
      if not can('manage_orders'): abort(403)
      ords = [{'id':o.id,**o.to_dict()}
              for o in get_db().collection('orders').order_by('created_at', direction='DESCENDING').stream()]
      return render_template('admin/orders.html', orders=ords)

  @app.route('/admin/custom-orders')
  @admin_required
  def admin_custom_orders():
      if not can('manage_orders'): abort(403)
      ords = [{'id':o.id,**o.to_dict()}
              for o in get_db().collection('custom_orders').order_by('created_at', direction='DESCENDING').stream()]
      return render_template('admin/custom_orders.html', orders=ords)

  @app.route('/admin/custom-orders/<oid>/status', methods=['POST'])
  @admin_required
  def admin_custom_order_status(oid):
      if not can('manage_orders'): abort(403)
      status = request.form.get('status')
      db = get_db()
      ref = db.collection('custom_orders').document(oid)
      ref.update({'status': status, 'updated_at': SERVER_TIMESTAMP})
      od = ref.get().to_dict()
      if od: notify(od.get('uid',''), 'Custom Order Update', f'Your order status: {status.replace("_"," ").title()}', 'info')
      log_admin('update_custom_order', {'oid': oid, 'status': status})
      flash('Status updated.', 'success')
      return redirect(url_for('admin_custom_orders'))

  @app.route('/admin/users')
  @admin_required
  def admin_users():
      if not can('manage_users'): abort(403)
      users = [{'id':u.id,**u.to_dict()} for u in get_db().collection('users').limit(200).stream()]
      return render_template('admin/users.html', users=users)

  @app.route('/admin/coupons')
  @admin_required
  def admin_coupons():
      if not can('manage_coupons'): abort(403)
      cpns = [{'id':c.id,**c.to_dict()} for c in get_db().collection('coupons').stream()]
      return render_template('admin/coupons.html', coupons=cpns)

  @app.route('/admin/coupons/new', methods=['POST'])
  @admin_required
  def admin_coupon_new():
      if not can('manage_coupons'): abort(403)
      f = request.form
      expiry = None
      if f.get('expiry'):
          try: expiry = datetime.strptime(f.get('expiry'), '%Y-%m-%d')
          except: pass
      get_db().collection('coupons').add({
          'code': f.get('code','').upper(), 'type': f.get('type','percentage'),
          'value': float(f.get('value', 0)), 'expiry_date': expiry,
          'usage_limit': int(f.get('limit', 9999)), 'usage_count': 0,
          'active': True, 'created_at': SERVER_TIMESTAMP
      })
      flash('Coupon created.', 'success')
      return redirect(url_for('admin_coupons'))

  @app.route('/admin/coupons/<cid>/delete', methods=['POST'])
  @admin_required
  def admin_coupon_delete(cid):
      if not can('manage_coupons'): abort(403)
      get_db().collection('coupons').document(cid).delete()
      flash('Coupon deleted.', 'success')
      return redirect(url_for('admin_coupons'))

  @app.route('/admin/legal')
  @admin_required
  def admin_legal():
      if not can('manage_settings'): abort(403)
      PAGES = ['privacy-policy','terms-of-service','refund-policy','cookie-policy','disclaimer','about-us']
      return render_template('admin/legal.html', pages=PAGES)

  @app.route('/admin/legal/<slug>', methods=['GET','POST'])
  @admin_required
  def admin_legal_edit(slug):
      if not can('manage_settings'): abort(403)
      db = get_db()
      doc = db.collection('legal_pages').document(slug).get()
      content = doc.to_dict().get('content','') if doc.exists else ''
      if request.method == 'POST':
          db.collection('legal_pages').document(slug).set(
              {'content': request.form.get('content',''), 'updated_at': SERVER_TIMESTAMP}, merge=True)
          log_admin('edit_legal', {'slug': slug})
          flash('Page updated.', 'success')
          return redirect(url_for('admin_legal'))
      return render_template('admin/legal_edit.html', slug=slug, content=content)

  @app.route('/admin/analytics')
  @admin_required
  def admin_analytics():
      if not can('manage_analytics'): abort(403)
      db = get_db()
      done = list(db.collection('orders').where('status','==','completed').stream())
      revenue = sum(float(o.to_dict().get('amount',0)) for o in done)
      pm = {}
      for o in done:
          pid = o.to_dict().get('product_id','')
          pm[pid] = pm.get(pid, 0) + 1
      top = []
      for pid, cnt in sorted(pm.items(), key=lambda x: x[1], reverse=True)[:5]:
          doc = db.collection('products').document(pid).get()
          if doc.exists:
              top.append({'name': doc.to_dict().get('name',''), 'count': cnt})
      ai_count = len(list(db.collection('ai_conversations').stream()))
      stats = {
          'revenue': revenue, 'orders': len(done),
          'users': len(list(db.collection('users').stream())),
          'products': len(list(db.collection('products').stream())),
          'ai': ai_count, 'top_products': top
      }
      return render_template('admin/analytics.html', stats=stats)

  @app.route('/admin/ai', methods=['GET','POST'])
  @admin_required
  def admin_ai():
      if not can('manage_settings'): abort(403)
      db = get_db()
      doc = db.collection('settings').document('ai').get()
      cfg = doc.to_dict() if doc.exists else {}
      if request.method == 'POST':
          db.collection('settings').document('ai').set({
              'name': request.form.get('name','CodeForge AI'),
              'welcome_message': request.form.get('welcome_message',''),
              'system_prompt': request.form.get('system_prompt',''),
              'enabled': 'enabled' in request.form,
              'model': request.form.get('model','gpt-3.5-turbo'),
              'updated_at': SERVER_TIMESTAMP
          }, merge=True)
          flash('AI settings saved.', 'success')
          return redirect(url_for('admin_ai'))
      return render_template('admin/ai.html', cfg=cfg)

  @app.route('/admin/settings', methods=['GET','POST'])
  @admin_required
  def admin_settings():
      if not can('manage_settings'): abort(403)
      db = get_db()
      doc = db.collection('settings').document('general').get()
      cfg = doc.to_dict() if doc.exists else {}
      if request.method == 'POST':
          db.collection('settings').document('general').set({
              'site_name': request.form.get('site_name','CodeForge'),
              'site_tagline': request.form.get('site_tagline',''),
              'currency': request.form.get('currency','INR'),
              'contact_email': request.form.get('contact_email',''),
              'imgbb_api_key': request.form.get('imgbb_api_key',''),
              'updated_at': SERVER_TIMESTAMP
          }, merge=True)
          flash('Settings saved.', 'success')
          return redirect(url_for('admin_settings'))
      return render_template('admin/settings.html', cfg=cfg)

  @app.route('/admin/admins')
  @admin_required
  @super_admin_required
  def admin_admins():
      admins = [{'id':a.id,**a.to_dict()} for a in get_db().collection('admins').stream()]
      return render_template('admin/admins.html', admins=admins)

  @app.route('/admin/admins/add', methods=['POST'])
  @admin_required
  @super_admin_required
  def admin_add_admin():
      email = request.form.get('email','').strip()
      role = request.form.get('role','admin')
      perms = request.form.getlist('permissions')
      db = get_db()
      try:
          user = get_auth().get_user_by_email(email)
          db.collection('admins').document(user.uid).set({
              'email': email, 'role': role, 'permissions': perms,
              'added_by': session.get('uid'), 'created_at': SERVER_TIMESTAMP
          })
          log_admin('add_admin', {'email': email})
          flash(f'{email} added as admin.', 'success')
      except Exception as e:
          flash(f'Error: {e}', 'error')
      return redirect(url_for('admin_admins'))

  @app.route('/admin/admins/<aid>/remove', methods=['POST'])
  @admin_required
  @super_admin_required
  def admin_remove_admin(aid):
      get_db().collection('admins').document(aid).delete()
      log_admin('remove_admin', {'aid': aid})
      flash('Admin removed.', 'success')
      return redirect(url_for('admin_admins'))

  @app.route('/admin/backup')
  @admin_required
  @super_admin_required
  def admin_backup():
      return render_template('admin/backup.html')

  @app.route('/admin/backup/create', methods=['POST'])
  @admin_required
  @super_admin_required
  def admin_backup_create():
      db = get_db()
      colls = request.form.getlist('colls') or ['products','orders','users','coupons','categories','legal_pages','settings']
      data = {}
      for c in colls:
          data[c] = [{'id':d.id, **{k:str(v) if hasattr(v,'timestamp') else v for k,v in d.to_dict().items()}}
                     for d in db.collection(c).stream()]
      bid = datetime.now().strftime('%Y%m%d_%H%M%S')
      db.collection('backups').document(bid).set({
          'data': json.dumps(data)[:900000],
          'collections': colls, 'created_at': SERVER_TIMESTAMP,
          'by': session.get('email','')
      })
      log_admin('create_backup', {'id': bid})
      flash(f'Backup {bid} created successfully.', 'success')
      return redirect(url_for('admin_backup'))

  @app.route('/admin/logs')
  @admin_required
  @super_admin_required
  def admin_logs():
      logs = [{'id':l.id,**l.to_dict()}
              for l in get_db().collection('admin_logs').order_by('timestamp', direction='DESCENDING').limit(100).stream()]
      return render_template('admin/logs.html', logs=logs)

  @app.route('/admin/categories', methods=['GET','POST'])
  @admin_required
  def admin_categories():
      if not can('manage_products'): abort(403)
      db = get_db()
      if request.method == 'POST':
          name = request.form.get('name','').strip()
          if name:
              db.collection('categories').add({'name': name, 'active': True, 'created_at': SERVER_TIMESTAMP})
              flash('Category added.', 'success')
          return redirect(url_for('admin_categories'))
      cats = [{'id':c.id,**c.to_dict()} for c in db.collection('categories').stream()]
      return render_template('admin/categories.html', categories=cats)

  @app.route('/admin/categories/<cid>/delete', methods=['POST'])
  @admin_required
  def admin_category_delete(cid):
      if not can('manage_products'): abort(403)
      get_db().collection('categories').document(cid).delete()
      flash('Deleted.', 'success')
      return redirect(url_for('admin_categories'))

  # ═══════════════════════════════════════════════════════════════
  # IMAGE UPLOAD (admin)
  # ═══════════════════════════════════════════════════════════════

  @app.route('/admin/upload', methods=['POST'])
  @admin_required
  @csrf.exempt
  def admin_upload():
      img = request.files.get('image')
      if not img:
          return jsonify({'error': 'No image'}), 400
      b64 = base64.b64encode(img.read()).decode()
      key = os.environ.get('IMGBB_API_KEY','')
      if not key:
          # Try settings
          doc = get_db().collection('settings').document('general').get()
          if doc.exists:
              key = doc.to_dict().get('imgbb_api_key','')
      if not key:
          return jsonify({'error': 'Image hosting not configured'}), 500
      try:
          r = requests.post('https://api.imgbb.com/1/upload', data={'key':key,'image':b64}, timeout=15)
          d = r.json()
          if d.get('success'):
              return jsonify({'url': d['data']['url']})
      except Exception as e:
          return jsonify({'error': str(e)}), 500
      return jsonify({'error': 'Upload failed'}), 500

  # ═══════════════════════════════════════════════════════════════
  # API
  # ═══════════════════════════════════════════════════════════════

  @app.route('/api/products')
  def api_products():
      cat = request.args.get('cat','')
      limit = min(int(request.args.get('limit',20)), 100)
      q = get_db().collection('products').where('active','==',True)
      if cat: q = q.where('category','==',cat)
      prods = [{k:v for k,v in {'id':p.id,**p.to_dict()}.items() if k != 'download_link'}
               for p in q.limit(limit).stream()]
      return jsonify({'products': prods, 'count': len(prods)})

  @app.route('/api/search')
  def api_search():
      q = request.args.get('q','').lower()
      if not q: return jsonify({'results':[]})
      results = []
      for p in get_db().collection('products').where('active','==',True).stream():
          d = p.to_dict()
          if q in d.get('name','').lower() or q in d.get('short_description','').lower():
              d.pop('download_link', None)
              results.append({'id':p.id,**d})
      return jsonify({'results': results[:20]})

  @app.route('/api/health')
  def api_health():
      return jsonify({'status':'ok','service':'CodeForge'})

  if __name__ == '__main__':
      port = int(os.environ.get('PORT', 5000))
      app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') == 'development')
  