# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fitness.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Модели базы данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    workouts = db.relationship('Workout', backref='user', lazy=True)
    goals = db.relationship('FitnessGoal', backref='user', lazy=True)

class Workout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    exercise_type = db.Column(db.String(100), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    sets = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FitnessGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exercise_type = db.Column(db.String(100), nullable=False)
    target_weight = db.Column(db.Float, nullable=False)
    target_reps = db.Column(db.Integer, nullable=False, default=1)
    target_sets = db.Column(db.Integer, nullable=False, default=1)
    current_weight = db.Column(db.Float, default=0.0)
    current_reps = db.Column(db.Integer, default=0)
    current_sets = db.Column(db.Integer, default=0)
    target_date = db.Column(db.Date, nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def progress_percentage(self):
        """Автоматически рассчитывает процент прогресса"""
        if self.target_weight <= 0:
            return 0
        progress = (self.current_weight / self.target_weight) * 100
        return min(progress, 100)
    
    def update_progress(self):
        """Обновляет прогресс на основе последних тренировок"""
        latest_workout = Workout.query.filter_by(
            user_id=self.user_id,
            exercise_type=self.exercise_type
        ).order_by(Workout.date.desc()).first()
        
        if latest_workout:
            self.current_weight = latest_workout.weight
            self.current_reps = latest_workout.reps
            self.current_sets = latest_workout.sets
            
            if (self.current_weight >= self.target_weight and 
                self.current_reps >= self.target_reps and 
                self.current_sets >= self.target_sets):
                self.is_completed = True

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Маршруты аутентификации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже существует')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неверные учетные данные')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Основные маршруты
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    thirty_days_ago = date.today() - timedelta(days=30)
    workouts = Workout.query.filter(
        Workout.user_id == current_user.id,
        Workout.date >= thirty_days_ago
    ).order_by(Workout.date.desc()).all()
    
    week_ago = date.today() - timedelta(days=7)
    week_workouts_count = Workout.query.filter(
        Workout.user_id == current_user.id,
        Workout.date >= week_ago
    ).count()
    
    goals = FitnessGoal.query.filter_by(user_id=current_user.id).all()
    
    # Подготовка данных для графика
    progress_data = {}
    user_workouts = Workout.query.filter_by(user_id=current_user.id).order_by(Workout.date).all()
    
    for workout in user_workouts:
        if workout.exercise_type not in progress_data:
            progress_data[workout.exercise_type] = {'dates': [], 'weights': []}
        progress_data[workout.exercise_type]['dates'].append(workout.date.isoformat())
        progress_data[workout.exercise_type]['weights'].append(workout.weight)
    
    return render_template('dashboard.html', 
                         workouts=workouts, 
                         today=date.today(),
                         week_workouts_count=week_workouts_count,
                         goals=goals,
                         progress_data=json.dumps(progress_data),
                         achievements=[])

@app.route('/add-workout', methods=['GET', 'POST'])
@login_required
def add_workout():
    if request.method == 'POST':
        try:
            workout_date = request.form['date']
            exercise_type = request.form['exercise_type']
            weight = float(request.form['weight'])
            reps = int(request.form['reps'])
            sets = int(request.form['sets'])
            
            workout = Workout(
                user_id=current_user.id,
                date=datetime.strptime(workout_date, '%Y-%m-%d').date(),
                exercise_type=exercise_type,
                weight=weight,
                reps=reps,
                sets=sets
            )
            
            db.session.add(workout)
            
            # Обновляем прогресс целей
            goals = FitnessGoal.query.filter_by(
                user_id=current_user.id,
                exercise_type=exercise_type
            ).all()
            
            for goal in goals:
                goal.update_progress()
            
            db.session.commit()
            flash('Тренировка успешно добавлена!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении тренировки: {str(e)}')
    
    return render_template('add_workout.html', today=date.today())

@app.route('/add-goal', methods=['GET', 'POST'])
@login_required
def add_goal():
    if request.method == 'POST':
        try:
            exercise_type = request.form['exercise_type']
            target_weight = float(request.form['target_weight'])
            target_reps = int(request.form.get('target_reps', 1))
            target_sets = int(request.form.get('target_sets', 1))
            target_date = datetime.strptime(request.form['target_date'], '%Y-%m-%d').date()
            
            goal = FitnessGoal(
                user_id=current_user.id,
                exercise_type=exercise_type,
                target_weight=target_weight,
                target_reps=target_reps,
                target_sets=target_sets,
                target_date=target_date
            )
            
            db.session.add(goal)
            db.session.commit()
            flash('Цель успешно добавлена!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении цели: {str(e)}')
    
    return render_template('add_goal.html', today=date.today())

@app.route('/advice')
@login_required
def advice():
    return render_template('advice.html')

@app.route('/update-progress/<int:goal_id>')
@login_required
def update_progress(goal_id):
    goal = FitnessGoal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('У вас нет доступа к этой цели')
        return redirect(url_for('dashboard'))
    
    try:
        goal.update_progress()
        db.session.commit()
        flash('Прогресс обновлен!')
    except Exception as e:
        flash(f'Ошибка при обновлении прогресса: {str(e)}')
    
    return redirect(url_for('dashboard'))


@app.route('/delete-goal/<int:goal_id>')
@login_required
def delete_goal(goal_id):
    goal = FitnessGoal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('У вас нет доступа к этой цели')
        return redirect(url_for('dashboard'))
    
    try:
        db.session.delete(goal)
        db.session.commit()
        flash('Цель успешно удалена!')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении цели: {str(e)}')
    
    return redirect(url_for('dashboard'))

# API маршруты
@app.route('/api/workout-stats/<period>')
@login_required
def workout_stats_period(period):
    end_date = date.today()
    
    if period == 'week':
        start_date = end_date - timedelta(days=7)
    elif period == 'month':
        start_date = end_date - timedelta(days=30)
    elif period == '3months':
        start_date = end_date - timedelta(days=90)
    else:
        start_date = end_date - timedelta(days=7)
    
    workouts = Workout.query.filter(
        Workout.user_id == current_user.id,
        Workout.date >= start_date,
        Workout.date <= end_date
    ).all()
    
    exercise_stats = {}
    for workout in workouts:
        if workout.exercise_type not in exercise_stats:
            exercise_stats[workout.exercise_type] = {
                'count': 0,
                'total_volume': 0,
                'max_weight': 0
            }
        
        exercise_stats[workout.exercise_type]['count'] += 1
        volume = workout.weight * workout.reps * workout.sets
        exercise_stats[workout.exercise_type]['total_volume'] += volume
        exercise_stats[workout.exercise_type]['max_weight'] = max(
            exercise_stats[workout.exercise_type]['max_weight'], 
            workout.weight
        )
    
    return jsonify({
        'period': period,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_workouts': len(workouts),
        'exercise_stats': exercise_stats
    })

@app.route('/api/calculate-progression', methods=['POST'])
@login_required
def calculate_progression():
    data = request.get_json()
    exercise_type = data.get('exercise_type')
    current_weight = float(data.get('current_weight'))
    target_weight = float(data.get('target_weight'))
    frequency = int(data.get('frequency', 2))
    
    weekly_increase = 0.025
    current = current_weight
    weeks = 0
    progression_data = []
    
    while current < target_weight and weeks < 104:
        weeks += 1
        if weeks > 12:
            effective_increase = weekly_increase * 0.7
        elif weeks > 24:
            effective_increase = weekly_increase * 0.5
        else:
            effective_increase = weekly_increase
            
        current += current * effective_increase
        progression_data.append({
            'week': weeks,
            'weight': round(current, 1),
            'increase_percent': round(effective_increase * 100, 1)
        })
    
    estimated_weeks = min(weeks, 104)
    estimated_months = round(estimated_weeks / 4.33, 1)
    
    return jsonify({
        'exercise': exercise_type,
        'current_weight': current_weight,
        'target_weight': target_weight,
        'estimated_weeks': estimated_weeks,
        'estimated_months': estimated_months,
        'progression_data': progression_data,
        'frequency': frequency
    })

@app.route('/api/calculate-calories', methods=['POST'])
@login_required
def calculate_calories():
    data = request.get_json()
    exercise_type = data.get('exercise_type')
    duration = int(data.get('duration', 60))
    user_weight = float(data.get('user_weight', 70))
    
    met_values = {
        'Жим лежа': 3.0,
        'Сведение рук в кроссовере на грудь': 2.8,
        'Разгибания на трицепс с канатной рукоятью в кроссовере': 3.0,
        'Сгибания на бицепс в РТ': 2.5,
        'Подъем на бицепс штанги обратным хватом': 3.0,
        'Ягодичный мост в РТ': 3.5,
        'Разгибание голени в БТ': 3.0,
        'Сгибание голени в БТ': 3.0,
        'Икроножные в Т': 2.5,
        'Вращения гантелей в согнутых руках': 2.5,
        'Вертикальная тяга сидя': 3.5,
        'Горизонтальная тяга': 3.5,
        'Экстензия': 4.0,
        'Сгибания в предплечьях': 2.0,
        'Работа с гирей на предплечья': 3.5
    }
    
    met = met_values.get(exercise_type, 3.0)
    calories = met * user_weight * (duration / 60)
    
    return jsonify({
        'exercise': exercise_type,
        'duration': duration,
        'met_value': met,
        'calories_burned': round(calories, 1),
        'user_weight': user_weight
    })

@app.route('/api/progress-data')
@login_required
def progress_data():
    workouts = Workout.query.filter_by(user_id=current_user.id).order_by(Workout.date).all()
    
    data = {}
    for workout in workouts:
        if workout.exercise_type not in data:
            data[workout.exercise_type] = {'dates': [], 'weights': []}
        
        data[workout.exercise_type]['dates'].append(workout.date.isoformat())
        data[workout.exercise_type]['weights'].append(workout.weight)
    
    return jsonify(data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)