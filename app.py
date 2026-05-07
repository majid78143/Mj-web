import os, jwt, json
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, make_response, flash, send_from_directory)
from models import db, bcrypt, User, AdminProfile, BotAccount, Log, AdminApplication, Broadcast
from config import (DATABASE_URI, SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_HOURS,
                    FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
                    MAX_BOTS_FREE, MAX_BOTS_PREMIUM, REFERRALS_REQUIRED_FOR_TCP)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = SECRET_KEY

db.init_app(app)
bcrypt.init_app(app)


# ─────────────────────────── HELPERS ────────────────────────────

def add_log(log_type, message, user_id=None, ip=None):
    entry = Log(user_id=user_id, log_type=log_type, message=message, ip=ip)
    db.session.add(entry)
    db.session.commit()


def create_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("token")
        if not token:
            return redirect(url_for("login"))
        data = decode_token(token)
        if not data:
            resp = make_response(redirect(url_for("login")))
            resp.delete_cookie("token")
            return resp
        user = User.query.get(data["user_id"])
        if not user:
            return redirect(url_for("login"))
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("token")
        if not token:
            return redirect(url_for("login"))
        data = decode_token(token)
        if not data:
            return redirect(url_for("login"))
        user = User.query.get(data["user_id"])
        if not user or user.role not in ("admin",):
            flash("Access denied.", "danger")
            return redirect(url_for("dashboard"))
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────── AUTH ────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    ref_code = request.args.get("ref", "")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ref      = request.form.get("ref", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("login.html", mode="register", ref=ref)

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already taken.", "danger")
            return render_template("login.html", mode="register", ref=ref)

        user = User(username=username, email=email)
        user.set_password(password)
        user.max_bots_allowed = MAX_BOTS_FREE

        if ref:
            referrer = User.query.filter_by(referral_code=ref).first()
            if referrer and referrer.email != email:
                user.referred_by = ref
                referrer.referral_count += 1
                referrer.credits += 10
                if referrer.referral_count >= REFERRALS_REQUIRED_FOR_TCP:
                    referrer.tcp_unlocked = True
                db.session.add(referrer)

        db.session.add(user)
        db.session.commit()
        add_log("login", f"New user registered: {username}", user_id=user.id,
                ip=request.remote_addr)
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("login.html", mode="register", ref=ref_code)


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html", mode="login")
        token = create_token(user.id)
        add_log("login", f"User logged in: {user.username}", user_id=user.id,
                ip=request.remote_addr)
        resp = make_response(redirect(url_for("dashboard")))
        resp.set_cookie("token", token, httponly=True,
                        max_age=int(timedelta(hours=JWT_EXPIRY_HOURS).total_seconds()))
        return resp
    return render_template("login.html", mode="login")


@app.route("/logout")
def logout():
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie("token")
    return resp


# ─────────────────────────── DASHBOARD ────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = request.current_user
    # auto-expire premium
    if user.is_premium and user.premium_expiry and datetime.utcnow() > user.premium_expiry:
        user.is_premium = False
        user.role = "user"
        db.session.commit()
    accounts = BotAccount.query.filter_by(user_id=user.id).all()
    return render_template("dashboard.html", user=user, accounts=accounts)


# ─────────────────────────── ACCOUNTS API ────────────────────────────

@app.route("/api/accounts", methods=["GET"])
@login_required
def api_accounts():
    user = request.current_user
    return jsonify([a.to_dict() for a in user.accounts])


@app.route("/api/accounts/add", methods=["POST"])
@login_required
def api_add_account():
    user = request.current_user
    if not user.tcp_unlocked:
        return jsonify({"error": "TCP not unlocked. Refer a friend or get admin approval."}), 403
    if len(user.accounts) >= user.max_bots_allowed:
        return jsonify({"error": f"Account limit reached ({user.max_bots_allowed})."}), 403

    data = request.get_json()
    uid      = data.get("uid", "").strip()
    region   = data.get("region", "").strip().upper()
    password = data.get("password", "").strip()
    if not uid or not region:
        return jsonify({"error": "UID and region are required."}), 400

    acc = BotAccount(user_id=user.id, uid=uid, region=region, password=password)
    db.session.add(acc)
    db.session.commit()
    add_log("tcp", f"Account added UID={uid} region={region}", user_id=user.id,
            ip=request.remote_addr)
    return jsonify(acc.to_dict()), 201


@app.route("/api/accounts/<int:acc_id>", methods=["DELETE"])
@login_required
def api_delete_account(acc_id):
    user = request.current_user
    acc = BotAccount.query.filter_by(id=acc_id, user_id=user.id).first_or_404()
    db.session.delete(acc)
    db.session.commit()
    return jsonify({"message": "Account deleted."})


@app.route("/api/accounts/<int:acc_id>/action", methods=["POST"])
@login_required
def api_account_action(acc_id):
    from bot_manager import bot_manager
    user = request.current_user
    acc  = BotAccount.query.filter_by(id=acc_id, user_id=user.id).first_or_404()
    action = request.get_json().get("action")
    if action == "start":
        result = bot_manager.start_bot(acc)
    elif action == "stop":
        result = bot_manager.stop_bot(acc.id)
    elif action == "restart":
        bot_manager.stop_bot(acc.id)
        result = bot_manager.start_bot(acc)
    else:
        return jsonify({"error": "Unknown action"}), 400
    add_log("bot", f"Bot {action} for UID={acc.uid}", user_id=user.id, ip=request.remote_addr)
    return jsonify(result)


# ─────────────────────────── ADMIN ────────────────────────────

@app.route("/admin")
@admin_required
def admin_panel():
    user  = request.current_user
    users = User.query.all()
    apps  = AdminApplication.query.filter_by(status="pending").all()
    logs  = Log.query.order_by(Log.created_at.desc()).limit(100).all()
    broadcasts = Broadcast.query.order_by(Broadcast.created_at.desc()).limit(20).all()
    admins = User.query.filter_by(role="admin").all()
    return render_template("admin.html", user=user, users=users,
                           apps=apps, logs=logs, broadcasts=broadcasts, admins=admins)


@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_admin_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/admin/users/<int:uid>", methods=["PATCH"])
@admin_required
def api_admin_edit_user(uid):
    me   = request.current_user
    if not me.admin_profile or not me.admin_profile.can_manage_users:
        return jsonify({"error": "No permission"}), 403
    user = User.query.get_or_404(uid)
    data = request.get_json()
    if "is_premium" in data:
        user.is_premium = bool(data["is_premium"])
        user.role = "premium" if user.is_premium else "user"
    if "premium_expiry" in data and data["premium_expiry"]:
        user.premium_expiry = datetime.fromisoformat(data["premium_expiry"])
    if "max_bots_allowed" in data:
        user.max_bots_allowed = int(data["max_bots_allowed"])
    if "tcp_unlocked" in data:
        user.tcp_unlocked = bool(data["tcp_unlocked"])
    if "credits" in data:
        user.credits = int(data["credits"])
    if "role" in data and data["role"] in ("user","premium","admin"):
        user.role = data["role"]
        if data["role"] == "admin" and not user.admin_profile:
            db.session.add(AdminProfile(user_id=user.id))
    db.session.commit()
    add_log("admin", f"Admin {me.username} edited user {user.username}", user_id=me.id)
    return jsonify(user.to_dict())


@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def api_admin_delete_user(uid):
    me   = request.current_user
    user = User.query.get_or_404(uid)
    if user.id == me.id:
        return jsonify({"error": "Cannot delete yourself"}), 400
    db.session.delete(user)
    db.session.commit()
    add_log("admin", f"Admin {me.username} deleted user {user.username}", user_id=me.id)
    return jsonify({"message": "User deleted."})


@app.route("/api/admin/applications", methods=["GET"])
@admin_required
def api_admin_applications():
    apps = AdminApplication.query.order_by(AdminApplication.created_at.desc()).all()
    return jsonify([a.to_dict() for a in apps])


@app.route("/api/admin/applications/<int:app_id>", methods=["PATCH"])
@admin_required
def api_admin_review_app(app_id):
    me  = request.current_user
    if not me.admin_profile or not me.admin_profile.can_approve_apps:
        return jsonify({"error": "No permission"}), 403
    appl   = AdminApplication.query.get_or_404(app_id)
    action = request.get_json().get("status")
    if action not in ("approved", "rejected"):
        return jsonify({"error": "Invalid status"}), 400
    appl.status = action
    if action == "approved":
        appl.applicant.role = "admin"
        if not appl.applicant.admin_profile:
            db.session.add(AdminProfile(user_id=appl.user_id))
    db.session.commit()
    add_log("admin", f"Application {app_id} {action} by {me.username}", user_id=me.id)
    return jsonify(appl.to_dict())


@app.route("/api/admin/broadcast", methods=["POST"])
@admin_required
def api_admin_broadcast():
    me   = request.current_user
    if not me.admin_profile or not me.admin_profile.can_send_broadcast:
        return jsonify({"error": "No permission"}), 403
    data    = request.get_json()
    message = data.get("message", "").strip()
    target  = data.get("target", "all")
    image   = data.get("image_url", None)
    if not message:
        return jsonify({"error": "Message is required"}), 400

    if target == "premium":
        recipients = User.query.filter_by(is_premium=True).all()
    elif target == "selected":
        ids = data.get("user_ids", [])
        recipients = User.query.filter(User.id.in_(ids)).all()
    else:
        recipients = User.query.all()

    from main import send_broadcast_telegram
    sent = send_broadcast_telegram(recipients, message, image)

    bc = Broadcast(sender_id=me.id, message=message, image_url=image,
                   target=target, sent_count=sent)
    db.session.add(bc)
    db.session.commit()
    add_log("broadcast", f"Broadcast sent to {sent} users by {me.username}", user_id=me.id)
    return jsonify({"message": f"Broadcast sent to {sent} users.", "broadcast": bc.to_dict()})


@app.route("/api/admin/logs", methods=["GET"])
@admin_required
def api_admin_logs():
    me = request.current_user
    if not me.admin_profile or not me.admin_profile.can_view_logs:
        return jsonify({"error": "No permission"}), 403
    log_type = request.args.get("type")
    q = Log.query.order_by(Log.created_at.desc())
    if log_type:
        q = q.filter_by(log_type=log_type)
    return jsonify([l.to_dict() for l in q.limit(500).all()])


@app.route("/api/admin/admins/<int:uid>/permissions", methods=["PATCH"])
@admin_required
def api_edit_admin_perms(uid):
    me   = request.current_user
    user = User.query.get_or_404(uid)
    if user.role != "admin":
        return jsonify({"error": "User is not an admin"}), 400
    prof = user.admin_profile
    if not prof:
        prof = AdminProfile(user_id=uid)
        db.session.add(prof)
    data = request.get_json()
    for perm in ("can_manage_users","can_manage_bots","can_send_broadcast",
                 "can_view_logs","can_edit_credits","can_approve_apps"):
        if perm in data:
            setattr(prof, perm, bool(data[perm]))
    db.session.commit()
    add_log("admin", f"Permissions updated for {user.username} by {me.username}", user_id=me.id)
    return jsonify(prof.to_dict())


@app.route("/api/admin/admins/<int:uid>", methods=["DELETE"])
@admin_required
def api_remove_admin(uid):
    me   = request.current_user
    user = User.query.get_or_404(uid)
    if user.id == me.id:
        return jsonify({"error": "Cannot remove yourself"}), 400
    user.role = "user"
    if user.admin_profile:
        db.session.delete(user.admin_profile)
    db.session.commit()
    add_log("admin", f"Admin {user.username} removed by {me.username}", user_id=me.id)
    return jsonify({"message": f"{user.username} demoted to user."})


@app.route("/api/admin/bots", methods=["GET"])
@admin_required
def api_admin_bots():
    me = request.current_user
    if not me.admin_profile or not me.admin_profile.can_manage_bots:
        return jsonify({"error": "No permission"}), 403
    accs = BotAccount.query.all()
    return jsonify([a.to_dict() for a in accs])


@app.route("/api/admin/bots/<int:acc_id>/stop", methods=["POST"])
@admin_required
def api_admin_force_stop(acc_id):
    from bot_manager import bot_manager
    result = bot_manager.stop_bot(acc_id)
    add_log("admin", f"Force-stopped bot #{acc_id} by {request.current_user.username}",
            user_id=request.current_user.id)
    return jsonify(result)


# ─────────────────────────── USER PROFILE API ────────────────────────────

@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    return jsonify(request.current_user.to_dict())


@app.route("/api/apply_admin", methods=["POST"])
@login_required
def api_apply_admin():
    user = request.current_user
    data = request.get_json()
    name       = data.get("name", "").strip()
    reason     = data.get("reason", "").strip()
    experience = data.get("experience", "").strip()
    if not name or not reason or not experience:
        return jsonify({"error": "All fields required"}), 400
    existing = AdminApplication.query.filter_by(user_id=user.id, status="pending").first()
    if existing:
        return jsonify({"error": "You already have a pending application"}), 409
    appl = AdminApplication(user_id=user.id, name=name, reason=reason, experience=experience)
    db.session.add(appl)
    db.session.commit()
    add_log("admin", f"Admin application submitted by {user.username}", user_id=user.id)
    return jsonify(appl.to_dict()), 201


# ─────────────────────────── STATIC ────────────────────────────

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


# ─────────────────────────── INIT ────────────────────────────

def create_tables():
    with app.app_context():
        db.create_all()
        # seed a default admin if none exists
        if not User.query.filter_by(role="admin").first():
            admin = User(username="admin", email="admin@localhost")
            admin.set_password("Admin@123")
            admin.role = "admin"
            admin.tcp_unlocked = True
            admin.max_bots_allowed = 999
            db.session.add(admin)
            db.session.flush()
            db.session.add(AdminProfile(
                user_id=admin.id,
                can_manage_users=True,
                can_manage_bots=True,
                can_send_broadcast=True,
                can_view_logs=True,
                can_edit_credits=True,
                can_approve_apps=True,
            ))
            db.session.commit()
            print("[INIT] Default admin created  email=admin@localhost  password=Admin@123")


if __name__ == "__main__":
    create_tables()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
