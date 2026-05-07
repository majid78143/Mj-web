from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
import uuid, string, random

db = SQLAlchemy()
bcrypt = Bcrypt()

def gen_referral_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


class User(db.Model):
    __tablename__ = "users"
    id              = db.Column(db.Integer, primary_key=True)
    username        = db.Column(db.String(64), unique=True, nullable=False)
    email           = db.Column(db.String(128), unique=True, nullable=False)
    password_hash   = db.Column(db.String(256), nullable=False)
    role            = db.Column(db.String(16), default="user")   # user / premium / admin
    is_premium      = db.Column(db.Boolean, default=False)
    premium_expiry  = db.Column(db.DateTime, nullable=True)
    max_bots_allowed= db.Column(db.Integer, default=1)
    referral_code   = db.Column(db.String(16), unique=True, default=gen_referral_code)
    referred_by     = db.Column(db.String(16), nullable=True)
    referral_count  = db.Column(db.Integer, default=0)
    credits         = db.Column(db.Integer, default=0)
    tcp_unlocked    = db.Column(db.Boolean, default=False)
    telegram_id     = db.Column(db.String(32), nullable=True, unique=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    accounts        = db.relationship("BotAccount", backref="owner", lazy=True, cascade="all, delete-orphan")
    logs            = db.relationship("Log", backref="user", lazy=True)
    admin_profile   = db.relationship("AdminProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    applications    = db.relationship("AdminApplication", backref="applicant", lazy=True)

    def set_password(self, pwd):
        self.password_hash = bcrypt.generate_password_hash(pwd).decode("utf-8")

    def check_password(self, pwd):
        return bcrypt.check_password_hash(self.password_hash, pwd)

    def is_premium_active(self):
        if not self.is_premium:
            return False
        if self.premium_expiry and datetime.utcnow() > self.premium_expiry:
            return False
        return True

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_premium": self.is_premium_active(),
            "premium_expiry": self.premium_expiry.isoformat() if self.premium_expiry else None,
            "max_bots_allowed": self.max_bots_allowed,
            "referral_code": self.referral_code,
            "referral_count": self.referral_count,
            "credits": self.credits,
            "tcp_unlocked": self.tcp_unlocked,
            "telegram_id": self.telegram_id,
            "created_at": self.created_at.isoformat(),
        }


class AdminProfile(db.Model):
    __tablename__ = "admin_profiles"
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    can_manage_users     = db.Column(db.Boolean, default=True)
    can_manage_bots      = db.Column(db.Boolean, default=True)
    can_send_broadcast   = db.Column(db.Boolean, default=False)
    can_view_logs        = db.Column(db.Boolean, default=True)
    can_edit_credits     = db.Column(db.Boolean, default=False)
    can_approve_apps     = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            "can_manage_users":   self.can_manage_users,
            "can_manage_bots":    self.can_manage_bots,
            "can_send_broadcast": self.can_send_broadcast,
            "can_view_logs":      self.can_view_logs,
            "can_edit_credits":   self.can_edit_credits,
            "can_approve_apps":   self.can_approve_apps,
        }


class BotAccount(db.Model):
    __tablename__ = "bot_accounts"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    uid         = db.Column(db.String(32), nullable=False)
    region      = db.Column(db.String(16), nullable=False)
    password    = db.Column(db.String(256), nullable=True)   # stored for re-login only
    status      = db.Column(db.String(16), default="offline")  # online / offline / running
    last_login  = db.Column(db.DateTime, nullable=True)
    token       = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "uid": self.uid,
            "region": self.region,
            "status": self.status,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat(),
        }


class Log(db.Model):
    __tablename__ = "logs"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    log_type    = db.Column(db.String(32), nullable=False)   # login / tcp / bot / admin / broadcast
    message     = db.Column(db.Text, nullable=False)
    ip          = db.Column(db.String(64), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "log_type": self.log_type,
            "message": self.message,
            "ip": self.ip,
            "created_at": self.created_at.isoformat(),
        }


class AdminApplication(db.Model):
    __tablename__ = "admin_applications"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name        = db.Column(db.String(128), nullable=False)
    reason      = db.Column(db.Text, nullable=False)
    experience  = db.Column(db.Text, nullable=False)
    status      = db.Column(db.String(16), default="pending")  # pending / approved / rejected
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.applicant.username if self.applicant else "?",
            "name": self.name,
            "reason": self.reason,
            "experience": self.experience,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class Broadcast(db.Model):
    __tablename__ = "broadcasts"
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    message     = db.Column(db.Text, nullable=False)
    image_url   = db.Column(db.String(512), nullable=True)
    target      = db.Column(db.String(16), default="all")    # all / premium / selected
    sent_count  = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "message": self.message,
            "image_url": self.image_url,
            "target": self.target,
            "sent_count": self.sent_count,
            "created_at": self.created_at.isoformat(),
        }
