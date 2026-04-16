import os
import random
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, AuditLog, MachineIdentity, Task, WorkShift, Leave

app = Flask(__name__)
app.config['SECRET_KEY'] = 'manufacturing-secret-key-v2'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///manufacturing_v2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_audit(action, user_id=None, username_attempt=None):
    ip_address = request.remote_addr
    log = AuditLog(
        user_id=user_id,
        username_attempt=username_attempt,
        action=action,
        ip_address=ip_address
    )
    db.session.add(log)
    db.session.commit()

with app.app_context():
    db.create_all()
    # Seed multiple machines for testing if they don't exist
    machines_to_seed = [
        "CNC-Milling-01",
        "Robotic-Arm-A2",
        "Conveyor-Belt-Main",
        "Quality-Scanner-X1",
        "Thermal-Processor-03"
    ]
    for m_name in machines_to_seed:
        if not MachineIdentity.query.filter_by(machine_name=m_name).first():
            hashed_key = generate_password_hash(f'key-{m_name}', method='scrypt')
            machine = MachineIdentity(machine_name=m_name, api_key_hash=hashed_key)
            db.session.add(machine)
    db.session.commit()


# --- Routes ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin': return redirect(url_for('admin_dashboard'))
        if current_user.role == 'manager': return redirect(url_for('manager_dashboard'))
        return redirect(url_for('worker_dashboard'))
    return render_template('welcome.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        if current_user.role == 'admin': return redirect(url_for('admin_dashboard'))
        if current_user.role == 'manager': return redirect(url_for('manager_dashboard'))
        return redirect(url_for('worker_dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        department = request.form.get('department')

        if role == 'worker' and not department:
            log_audit("Failed Registration: Missing department for worker", username_attempt=username)
            flash('Workers must select a valid department. Managers/Admins can ignore it.', 'error')
            return redirect(url_for('signup'))

        user = User.query.filter_by(username=username).first()

        if user:
            log_audit(f"Failed Registration: Username '{username}' already exists", username_attempt=username)
            flash('Username already exists. Please log in.', 'error')
            return redirect(url_for('signup'))

        new_user = User(
            username=username, 
            password_hash=generate_password_hash(password, method='scrypt'),
            role=role if role else 'worker',
            department=department
        )
        db.session.add(new_user)
        db.session.commit()
        
        log_audit("Account Created Successfully", user_id=new_user.id)
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin': return redirect(url_for('admin_dashboard'))
        if current_user.role == 'manager': return redirect(url_for('manager_dashboard'))
        return redirect(url_for('worker_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            log_audit(f"Failed Login Attempt for '{username}'", username_attempt=username)
            flash('Please check your login details and try again.', 'error')
            return redirect(url_for('login'))

        otp = str(random.randint(100000, 999999))
        session['pending_user_id'] = user.id
        session['expected_otp'] = otp
        flash(f'Simulated SMS: Your verification code is {otp}', 'info')
        return redirect(url_for('verify_otp'))

    return render_template('login.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if 'pending_user_id' not in session:
        flash('Please login first.', 'error')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        user_entered_otp = request.form.get('otp')
        expected_otp = session.get('expected_otp')
        
        if user_entered_otp == expected_otp:
            user_id = session.get('pending_user_id')
            user = User.query.get(user_id)
            login_user(user)
            log_audit("Successful Login (MFA verified)", user_id=user.id)
            
            session.pop('pending_user_id', None)
            session.pop('expected_otp', None)
            
            if user.role == 'admin': return redirect(url_for('admin_dashboard'))
            if user.role == 'manager': return redirect(url_for('manager_dashboard'))
            return redirect(url_for('worker_dashboard'))
        else:
            flash('Invalid verification code. Please try again.', 'error')
            
    return render_template('verify_otp.html')

@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if 'pending_user_id' not in session:
        flash('Please login first.', 'error')
        return redirect(url_for('login'))
        
    otp = str(random.randint(100000, 999999))
    session['expected_otp'] = otp
    flash(f'Simulated SMS Resend: Your new verification code is {otp}', 'info')
    return redirect(url_for('verify_otp'))

@app.route('/logout')
@login_required
def logout():
    uid = current_user.id
    logout_user()
    log_audit("Logged Out", user_id=uid)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Deprecated: Redirects to correct role-based dashboard
    if current_user.role == 'admin': return redirect(url_for('admin_dashboard'))
    if current_user.role == 'manager': return redirect(url_for('manager_dashboard'))
    return redirect(url_for('worker_dashboard'))

@app.route('/worker_dashboard')
@login_required
def worker_dashboard():
    if current_user.role != 'worker':
        return redirect(url_for('dashboard'))
    
    # Needs to see today's shift
    today = datetime.utcnow().date()
    today_shift = WorkShift.query.filter_by(user_id=current_user.id, shift_date=today).first()
    
    # Tasks and leaves
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.date_assigned.desc()).all()
    leaves = Leave.query.filter_by(user_id=current_user.id).order_by(Leave.start_date.desc()).all()
    
    return render_template('worker_dashboard.html', shift=today_shift, tasks=tasks, leaves=leaves)

@app.route('/manager_dashboard')
@login_required
def manager_dashboard():
    if current_user.role not in ['manager', 'admin']:
        flash('Access Denied.', 'error')
        return redirect(url_for('dashboard'))
    
    workers = User.query.filter_by(role='worker').all()
    auth_logs = AuditLog.query.filter(AuditLog.action.in_(["Successful Login", "Logged Out"])).order_by(AuditLog.timestamp.desc()).limit(50).all()
    machines = MachineIdentity.query.all()
    
    return render_template('manager_dashboard.html', workers=workers, logs=auth_logs, machines=machines)

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        log_audit("Unauthorized Admin Access Attempt", user_id=current_user.id)
        flash('Access Denied. You do not have the required authorization.', 'error')
        return redirect(url_for('dashboard'))
        
    workers = User.query.filter_by(role='worker').all()
    managers = User.query.filter_by(role='manager').all()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(20).all()
    leaves = Leave.query.order_by(Leave.start_date.desc()).all()
    return render_template('admin_dashboard.html', workers=workers, managers=managers, logs=logs, leaves=leaves)

@app.route('/admin/assign_work', methods=['POST'])
@login_required
def assign_work():
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    user_id = request.form.get('user_id')
    description = request.form.get('description')
    shift_date_str = request.form.get('shift_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    
    if user_id and description and shift_date_str and start_time and end_time:
        shift_date = datetime.strptime(shift_date_str, '%Y-%m-%d').date()
        shift = WorkShift(user_id=user_id, shift_date=shift_date, start_time=start_time, end_time=end_time)
        task = Task(user_id=user_id, description=description)
        db.session.add(shift)
        db.session.add(task)
        db.session.commit()
        flash('Shift and task assigned successfully.', 'success')
    else:
        flash('Missing fields. Please fill all inputs.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_worker/<int:user_id>', methods=['POST'])
@login_required
def delete_worker(user_id):
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    user = User.query.get_or_404(user_id)
    if user.role == 'worker':
        # Clean up related records
        Task.query.filter_by(user_id=user_id).delete()
        WorkShift.query.filter_by(user_id=user_id).delete()
        Leave.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'Worker {user.username} deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/request_leave', methods=['POST'])
@login_required
def request_leave():
    if current_user.role != 'worker':
        return jsonify({"error": "Unauthorized"}), 403
    
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    reason = request.form.get('reason')
    
    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        leave = Leave(user_id=current_user.id, start_date=start_date, end_date=end_date, reason=reason, status='Pending')
        db.session.add(leave)
        db.session.commit()
        flash('Leave request submitted successfully.', 'success')
    return redirect(url_for('worker_dashboard'))

@app.route('/admin/update_leave/<int:leave_id>', methods=['POST'])
@login_required
def update_leave(leave_id):
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
        
    leave = Leave.query.get_or_404(leave_id)
    new_status = request.form.get('status')
    
    if new_status in ['Approved', 'Rejected']:
        leave.status = new_status
        db.session.commit()
        flash(f'Leave request updated to {new_status}.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/telemetry', methods=['POST'])
def api_telemetry():
    api_key = request.headers.get('Machine-API-Key')
    if not api_key:
        return jsonify({"error": "Missing Machine-API-Key header"}), 401

    machines = MachineIdentity.query.all()
    authenticated_machine = None
    for machine in machines:
        if check_password_hash(machine.api_key_hash, api_key):
            authenticated_machine = machine
            break

    if not authenticated_machine:
        log_audit("Failed IoT Telemetry Authentication (Invalid API Key)")
        return jsonify({"error": "Invalid API Key"}), 403

    authenticated_machine.last_seen = datetime.utcnow()
    db.session.commit()
    
    # Process telemetry (dummy logic)
    data = request.json
    return jsonify({"status": "success", "machine": authenticated_machine.machine_name, "received_data": data}), 200

@app.route('/api/stats')
@login_required
def api_stats():
    # Returns random telemetry data for the charts
    return jsonify({
        "temperature": [random.randint(60, 90) for _ in range(10)],
        "vibration": [random.randint(10, 50) for _ in range(10)],
        "labels": [f"T-{i}s" for i in range(10, 0, -1)]
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
