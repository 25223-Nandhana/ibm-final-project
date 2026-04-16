from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='worker')  # Roles: 'worker', 'admin', 'manager'
    department = db.Column(db.String(100), nullable=True)
    logs = db.relationship('AuditLog', backref='user', lazy=True)
    shifts = db.relationship('WorkShift', backref='user', lazy=True)
    tasks = db.relationship('Task', backref='user', lazy=True)
    leaves = db.relationship('Leave', backref='user', lazy=True)

class WorkShift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shift_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=False) # e.g. "09:00 AM"
    end_time = db.Column(db.String(10), nullable=False)   # e.g. "05:00 PM"

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='Assigned') # Assigned, In Progress, Completed
    date_assigned = db.Column(db.DateTime, default=datetime.utcnow)

class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), default='Pending') # Pending, Approved, Rejected

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Could be anonymous on failure
    username_attempt = db.Column(db.String(100)) # Store username if login failed
    action = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class MachineIdentity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    machine_name = db.Column(db.String(100), unique=True, nullable=False)
    api_key_hash = db.Column(db.String(200), nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
