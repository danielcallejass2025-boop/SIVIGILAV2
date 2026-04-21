from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .security import decrypt_visible_password, encrypt_visible_password, is_visible_password_encrypted


class UserRole:
    SECRETARIO = "SECRETARIO"
    EPIDEMIOLOGO = "EPIDEMIOLOGO"


class BulletinStatus:
    BORRADOR = "BORRADOR"
    PUBLICADO = "PUBLICADO"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    password_visible = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(30), nullable=False, index=True)

    full_name = db.Column(db.String(150), nullable=False)
    cedula = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    assigned_event_code = db.Column(db.Integer, db.ForeignKey("events.code"), nullable=True)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    credentials_updated_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    bulletins = db.relationship("Bulletin", back_populates="author", lazy=True)

    def set_password(self, plain_password: str) -> None:
        self.password_hash = generate_password_hash(plain_password)

    def check_password(self, plain_password: str) -> bool:
        return check_password_hash(self.password_hash, plain_password)

    def set_visible_password(self, plain_password: str | None) -> None:
        self.password_visible = encrypt_visible_password(plain_password)

    @property
    def password_visible_plain(self) -> str:
        return decrypt_visible_password(self.password_visible)

    def has_encrypted_visible_password(self) -> bool:
        return is_visible_password_encrypted(self.password_visible)


class Event(db.Model):
    __tablename__ = "events"

    code = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    users = db.relationship("User", backref="assigned_event", lazy=True)
    bulletins = db.relationship("Bulletin", back_populates="event", lazy=True)


class Bulletin(db.Model):
    __tablename__ = "bulletins"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=BulletinStatus.BORRADOR)

    event_code = db.Column(db.Integer, db.ForeignKey("events.code"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", back_populates="bulletins")
    event = db.relationship("Event", back_populates="bulletins")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    entity = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(80), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", lazy=True)
