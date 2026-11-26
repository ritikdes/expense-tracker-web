from flask import render_template, request, flash, redirect, url_for, Response
from models import db, User, Expense, app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
import math, io, csv
from sqlalchemy import func
import os

with app.app_context():
    db.create_all()

app.secret_key = os.environ.get("SECRET_KEY", "dev-key-only")
CATEGORIES = ["Food", "Entertainment", "Utilities", "Shopping", "Transportation", "Others"]

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route("/")
@login_required
def index():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    total_amount = sum(e.amount for e in expenses)
    return render_template("index.html", expenses=expenses, total_amount=total_amount, categories=CATEGORIES, user_id=current_user.id)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        has_error = False
        if not username or not password:
            flash("Please fill out all fields.", "danger")
            return render_template("register.html")

        user = User.query.filter_by(username=username).first()
        if user:
            has_error = True
            flash("Username exists!", "danger")

        if len(password) < 8:
            has_error = True
            flash("Too short password", "danger")

        if not has_error:
            hashed_pw = generate_password_hash(password)
            new_user = User(username=username, password_hash=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            flash("User added!", "success")

            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Please fill out all fields.", "danger")
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password!", "danger")
            return render_template("login.html")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have logged out!", "success")
    return redirect(url_for("login"))


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        amount_str = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        date_str = request.form.get("date", "").strip()

        has_error = False

        if category not in CATEGORIES:
            flash("Invalid category", "danger")
            has_error = True

        try:
            amount = float(amount_str)
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError("Invalid amount")
        except ValueError:
            flash("Enter valid number", "danger")
            has_error = True

        if not date_str:
            expense_date = date.today()
        else:
            try:
                expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date!", "danger")
                has_error = True

        if not has_error:
            new_expense = Expense(amount=amount, category=category, description=description, date=expense_date, user_id=current_user.id)
            db.session.add(new_expense)
            db.session.commit()
            flash("Expense added!", "success")
            return redirect(url_for("index"))
    return render_template("add.html", categories=CATEGORIES, date=date.today().isoformat())


@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()

    db.session.delete(expense)
    flash("Expense deleted!", "success")
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()

    if request.method == "GET":
        return render_template("edit.html", expense=expense, categories=CATEGORIES)

    if request.method == "POST":
        amount_str = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        date_str = request.form.get("date", "").strip()

        has_error = False

        try:
            amount = float(amount_str)
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError("Invalid amount")
        except (TypeError, ValueError):
            flash("Enter valid number", "danger")
            has_error = True

        if not date_str:
            expense_date = date.today()
        else:
            try:
                expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date", "danger")
                has_error = True

        if category not in CATEGORIES:
            flash("Invalid category", "danger")
            has_error = True

        if not has_error:
            expense.amount = amount
            expense.category = category
            expense.description = description
            expense.date = expense_date
            db.session.commit()
            flash("Edit successful", "success")
            return redirect(url_for("index"))
        
        return render_template("edit.html", expense=expense, categories=CATEGORIES)


@app.route("/summary", methods=["GET"])
@login_required
def summary():
    total = db.session.query(func.sum(Expense.amount)).filter_by(user_id=current_user.id).scalar() or 0.0
    highest = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.amount.desc()).first()
    breakdown_query = db.session.query(Expense.category, func.sum(Expense.amount)).filter_by(user_id=current_user.id).group_by(Expense.category).all()
    breakdown = {cat: amt for cat, amt in breakdown_query}

    return render_template("summary.html",total=total, highest=highest, breakdown=breakdown)


@app.route("/filter", methods=["GET"])
@login_required
def filter_by_date():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    filtered_expenses = []

    if start_date and end_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()

            if s_date > e_date:
                flash("Start date cannot be later than end date.", "danger")
                return render_template("filter.html", expenses=[])

            filtered_expenses = Expense.query.filter_by(user_id=current_user.id).filter(
                Expense.date >= s_date,
                Expense.date <= e_date
            ).order_by(Expense.date.desc()).all()
        except ValueError:
            flash("Invalid date format", "danger")
    return render_template("filter.html", expenses=filtered_expenses)


@app.route("/export")
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['Id', "Date", 'Category', 'Amount', 'Description'])

    for e in expenses:
        writer.writerow([e.id, e.date, e.category, e.amount, e.description])

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=expenses.csv"}
    )

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(debug=debug_mode)