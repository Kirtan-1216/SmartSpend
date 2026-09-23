import csv
import os
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps
from io import StringIO

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from db_manager import (
    add_user,
    check_user,
    create_table,
    delete_expense_with_history,
    get_budget_limit,
    get_category_totals,
    get_expense,
    get_insights,
    get_last_7_days_spending,
    get_monthly_trend,
    get_username,
    insert_expense,
    is_unusual_expense,
    total_expense,
    update_budget_limit,
    update_expense,
    update_savings_goal,
    view_delete_history,
    view_expenses,
)
from nlp_utils import process_natural_language


def _load_or_create_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    secret_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    if os.path.exists(secret_path):
        with open(secret_path, "r", encoding="utf-8") as handle:
            stored = handle.read().strip()
            if stored:
                return stored
    generated = secrets.token_hex(32)
    with open(secret_path, "w", encoding="utf-8") as handle:
        handle.write(generated)
    return generated


def create_app():
    application = Flask(__name__)
    application.secret_key = _load_or_create_secret_key()
    application.permanent_session_lifetime = timedelta(days=30)
    application.config["SESSION_COOKIE_HTTPONLY"] = True
    application.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
        application.config["SESSION_COOKIE_SECURE"] = True
    create_table()
    return application


app = create_app()

VALID_CATEGORIES = [
    "Food",
    "Transport",
    "Utilities",
    "Entertainment",
    "Health",
    "Shopping",
    "Stationery",
    "Furniture",
    "Education",
    "Salary",
    "Income",
    "Miscellaneous",
]


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "USER_ID" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def ensure_csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.context_processor
def inject_globals():
    return {
        "csrf_token": ensure_csrf(),
        "valid_categories": VALID_CATEGORIES,
    }


@app.before_request
def csrf_protect():
    if app.config.get("TESTING"):
        return
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("_csrf"):
            abort(400)


def parse_amount(raw_value):
    try:
        amount = float(raw_value)
    except (TypeError, ValueError):
        return None
    if amount <= 0 or amount > 1_000_000_000:
        return None
    return round(amount, 2)


def parse_date(raw_value):
    if not raw_value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_value):
        return raw_value
    return None


def normalize_category(raw_value):
    category = (raw_value or "").strip()
    if not category:
        return "Miscellaneous"
    return category[:40]


def normalize_username(raw_value):
    return (raw_value or "").strip()


def valid_password(raw_value):
    return bool(raw_value) and 6 <= len(raw_value) <= 128


def after_save_alerts(user_id, category, amount, tx_type):
    if tx_type != "expense":
        return
    unusual, average = is_unusual_expense(user_id, category, amount)
    if unusual:
        flash(
            f"High spending notice: ₹{amount:.2f} on {category} is much higher than your usual ₹{average:.2f}.",
            "error",
        )
    budget = get_budget_limit(user_id)
    if budget > 0:
        month = datetime.now().strftime("%Y-%m")
        spent = total_expense(user_id, month)
        if spent > budget:
            flash(
                f"BUDGET EXCEEDED: This month's spending (₹{spent:.2f}) passed the ₹{budget:.2f} limit.",
                "error",
            )
        elif spent >= budget * 0.8:
            flash(
                f"Budget warning: you have used {(spent / budget) * 100:.0f}% of this month's ₹{budget:.2f} limit.",
                "error",
            )


@app.route("/")
@login_required
def home():
    user_id = session["USER_ID"]
    name = get_username(user_id)
    records = view_expenses(user_id)
    insights = get_insights(user_id)
    return render_template(
        "ssindex.html",
        expenses=records,
        user_name=name,
        insights=insights,
        total_val=insights["all_expense"],
        budget=insights["budget"],
        today=datetime.now().strftime("%Y-%m-%d"),
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "USER_ID" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        username = normalize_username(request.form.get("username"))
        password = request.form.get("password") or ""
        if not username or len(username) < 3 or len(username) > 40:
            flash("Username must be 3 to 40 characters.", "error")
        elif not valid_password(password):
            flash("Password must be at least 6 characters.", "error")
        elif add_user(username, password):
            user_id = check_user(username, password)
            session.clear()
            session.permanent = True
            session["USER_ID"] = user_id
            ensure_csrf()
            flash("Account created successfully!", "success")
            return redirect(url_for("home"))
        else:
            flash("Username already taken! Please choose another.", "error")
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "USER_ID" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        username = normalize_username(request.form.get("username"))
        password = request.form.get("password")
        user_id = check_user(username, password)
        if user_id:
            session.clear()
            session.permanent = True
            session["USER_ID"] = user_id
            ensure_csrf()
            flash("Logged in successfully!", "success")
            return redirect(url_for("home"))
        flash("Invalid username or password", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/add", methods=["POST"])
@login_required
def add():
    category = normalize_category(request.form.get("category"))
    amount = parse_amount(request.form.get("amount"))
    tx_date = parse_date(request.form.get("date")) or None
    description = (request.form.get("description") or "").strip()[:120]
    tx_type = "income" if request.form.get("tx_type") == "income" else "expense"

    if amount is None:
        flash("Please enter a valid amount greater than 0.", "error")
        return redirect(url_for("home"))

    if insert_expense(session["USER_ID"], category, amount, tx_date, description, tx_type):
        flash(f"{tx_type.capitalize()} added successfully!", "success")
        after_save_alerts(session["USER_ID"], category, amount, tx_type)
    else:
        flash("Error saving transaction.", "error")
    return redirect(url_for("home"))


@app.route("/smart_add", methods=["POST"])
@login_required
def smart_add():
    smart_text = (request.form.get("smart_input") or "").strip()
    if not smart_text:
        flash("Please type a sentence such as 'Spent 500 on dinner yesterday'.", "error")
        return redirect(url_for("home"))

    parsed = process_natural_language(smart_text)
    amount = parse_amount(parsed.get("amount"))
    if amount is None:
        flash("Could not detect a valid amount. Please modify your text.", "error")
        return redirect(url_for("home"))

    category = normalize_category(parsed.get("category"))
    tx_type = parsed.get("tx_type") or "expense"
    tx_date = parsed.get("date")
    description = parsed.get("description") or smart_text

    if insert_expense(session["USER_ID"], category, amount, tx_date, description, tx_type):
        flash(
            f"Smart added {tx_type}: ₹{amount:.2f} for {category} on {tx_date}.",
            "success",
        )
        after_save_alerts(session["USER_ID"], category, amount, tx_type)
    else:
        flash("Error saving expense from smart input.", "error")
    return redirect(url_for("home"))


@app.route("/api/parse", methods=["POST"])
@login_required
def api_parse():
    text = ""
    if request.is_json:
        text = ((request.json or {}).get("text") or "").strip()
    else:
        text = (request.form.get("smart_input") or "").strip()
    return jsonify(process_natural_language(text))


@app.route("/history")
@login_required
def history():
    user_id = session["USER_ID"]
    name = get_username(user_id)
    deleted_items = view_delete_history(user_id)
    return render_template("history.html", history=deleted_items, user_name=name)


@app.route("/summary")
@login_required
def summary():
    user_id = session["USER_ID"]
    name = get_username(user_id)
    insights = get_insights(user_id)
    return render_template("summary.html", user_name=name, insights=insights)


@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    if delete_expense_with_history(id, session["USER_ID"]):
        flash("Transaction deleted successfully!", "success")
    else:
        flash("Failed to delete transaction.", "error")
    return redirect(url_for("home"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit(id):
    record = get_expense(id, session["USER_ID"])
    if not record:
        flash("Transaction not found.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        category = normalize_category(request.form.get("category"))
        amount = parse_amount(request.form.get("amount"))
        tx_date = parse_date(request.form.get("date"))
        description = (request.form.get("description") or "").strip()[:120]
        tx_type = "income" if request.form.get("tx_type") == "income" else "expense"
        if amount is None or not tx_date:
            flash("Please provide a valid amount and date.", "error")
        elif update_expense(id, session["USER_ID"], category, amount, tx_date, description, tx_type):
            flash("Transaction updated successfully!", "success")
            return redirect(url_for("home"))
        else:
            flash("Failed to update transaction.", "error")
    return render_template("edit.html", record=record, user_name=get_username(session["USER_ID"]))


@app.route("/api/data")
@login_required
def api_data():
    user_id = session["USER_ID"]
    cat_data = get_category_totals(user_id, month=None, tx_type="expense")
    days_data = get_last_7_days_spending(user_id)
    months_data = get_monthly_trend(user_id)
    insights = get_insights(user_id)
    return jsonify(
        {
            "categories": {row[0]: row[1] for row in cat_data},
            "days": {row[0]: row[1] for row in days_data},
            "months": {row[0]: row[1] for row in months_data},
            "summary": {
                "month_income": insights["month_income"],
                "month_expense": insights["month_expense"],
                "month_balance": insights["month_balance"],
                "all_income": insights["all_income"],
                "all_expense": insights["all_expense"],
                "balance": insights["balance"],
            },
        }
    )


def parse_money_or_zero(raw_value):
    if raw_value in (None, ""):
        return 0.0
    try:
        amount = float(raw_value)
    except (TypeError, ValueError):
        return None
    if amount < 0 or amount > 1_000_000_000:
        return None
    return round(amount, 2)


@app.route("/settings", methods=["POST"])
@login_required
def settings():
    budget = parse_money_or_zero(request.form.get("budget_limit"))
    goal = parse_money_or_zero(request.form.get("savings_goal"))

    ok = True
    if budget is None:
        flash("Please enter a valid budget amount (or 0 to disable).", "error")
        ok = False
    elif not update_budget_limit(session["USER_ID"], budget):
        flash("Failed to update budget limit.", "error")
        ok = False

    if goal is None:
        flash("Please enter a valid savings goal (or 0 to disable).", "error")
        ok = False
    elif not update_savings_goal(session["USER_ID"], goal):
        flash("Failed to update savings goal.", "error")
        ok = False

    if ok:
        flash("Settings saved.", "success")
    return redirect(url_for("home"))


@app.route("/export")
@login_required
def export_csv():
    records = view_expenses(session["USER_ID"])
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["ID", "Type", "Category", "Amount", "Date", "Description"])
    for row in records:
        writer.writerow(
            [row["id"], row["tx_type"], row["CATEGORY"], row["AMOUNT"], row["DATE"], row["description"]]
        )
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=smartspend.csv"},
    )


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "true").lower() in ("1", "true", "yes")
    app.run(debug=debug)
