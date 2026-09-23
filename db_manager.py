import os
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash

# Always use the database next to this file, not whatever folder the server was started from.
# A relative path like "finance_tracker.db" was a common reason data seemed to "disappear".
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SMARTSPEND_DB") or os.path.join(BASE_DIR, "finance_tracker.db")


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_table():
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL)"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            USER_ID INTEGER NOT NULL,
            CATEGORY TEXT NOT NULL,
            AMOUNT REAL NOT NULL,
            DATE TEXT NOT NULL,
            FOREIGN KEY (USER_ID) REFERENCES users (id))"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS delete_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            USER_ID INTEGER NOT NULL,
            CATEGORY TEXT NOT NULL,
            AMOUNT REAL NOT NULL,
            EXPENSE_DATE TEXT NOT NULL,
            DELETED_AT TEXT NOT NULL,
            FOREIGN KEY (USER_ID) REFERENCES users (id))"""
        )

        _add_column_if_missing(cursor, "users", "budget_limit", "REAL DEFAULT 0.0")
        _add_column_if_missing(cursor, "users", "savings_goal", "REAL DEFAULT 0.0")
        _add_column_if_missing(cursor, "expenses", "description", "TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "expenses", "tx_type", "TEXT DEFAULT 'expense'")
        _add_column_if_missing(cursor, "delete_history", "description", "TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "delete_history", "tx_type", "TEXT DEFAULT 'expense'")

        connection.commit()


def add_user(username, password):
    try:
        hashed_pw = generate_password_hash(password)
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_pw),
            )
            connection.commit()
            return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error:
        return False


def check_user(username, password):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            if result and check_password_hash(result["password"], password):
                return result["id"]
            return None
    except sqlite3.Error:
        return None


def insert_expense(USER_ID, category, amount, date=None, description="", tx_type="expense"):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    tx_type = "income" if str(tx_type).lower() == "income" else "expense"
    description = (description or "").strip()
    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO expenses (USER_ID, CATEGORY, AMOUNT, DATE, description, tx_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (USER_ID, category.strip(), float(amount), date, description, tx_type),
            )
            connection.commit()
            return True
    except (sqlite3.Error, ValueError, TypeError):
        return False


def delete_expense(expense_id, user_id=None):
    """Legacy helper. Prefer delete_expense_with_history so deletes stay user-scoped."""
    try:
        with get_connection() as connection:
            if user_id is None:
                connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            else:
                connection.execute(
                    "DELETE FROM expenses WHERE id = ? AND USER_ID = ?",
                    (expense_id, user_id),
                )
            connection.commit()
            return True
    except sqlite3.Error:
        return False


def view_expenses(USER_ID, tx_type=None):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            if tx_type:
                cursor.execute(
                    """SELECT id, USER_ID, CATEGORY, AMOUNT, DATE,
                              COALESCE(description, '') AS description,
                              COALESCE(tx_type, 'expense') AS tx_type
                       FROM expenses
                       WHERE USER_ID = ? AND COALESCE(tx_type, 'expense') = ?
                       ORDER BY DATE DESC, id DESC""",
                    (USER_ID, tx_type),
                )
            else:
                cursor.execute(
                    """SELECT id, USER_ID, CATEGORY, AMOUNT, DATE,
                              COALESCE(description, '') AS description,
                              COALESCE(tx_type, 'expense') AS tx_type
                       FROM expenses
                       WHERE USER_ID = ?
                       ORDER BY DATE DESC, id DESC""",
                    (USER_ID,),
                )
            return cursor.fetchall()
    except sqlite3.Error:
        return []


def get_expense(expense_id, user_id):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT id, USER_ID, CATEGORY, AMOUNT, DATE,
                          COALESCE(description, '') AS description,
                          COALESCE(tx_type, 'expense') AS tx_type
                   FROM expenses WHERE id = ? AND USER_ID = ?""",
                (expense_id, user_id),
            )
            return cursor.fetchone()
    except sqlite3.Error:
        return None


def update_expense(expense_id, user_id, category, amount, date, description="", tx_type="expense"):
    tx_type = "income" if str(tx_type).lower() == "income" else "expense"
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE expenses
                   SET CATEGORY = ?, AMOUNT = ?, DATE = ?, description = ?, tx_type = ?
                   WHERE id = ? AND USER_ID = ?""",
                (category.strip(), float(amount), date, (description or "").strip(), tx_type, expense_id, user_id),
            )
            connection.commit()
            return cursor.rowcount == 1
    except (sqlite3.Error, ValueError, TypeError):
        return False


def total_expense(USER_ID, month=None):
    return _sum_amount(USER_ID, "expense", month)


def total_income(USER_ID, month=None):
    return _sum_amount(USER_ID, "income", month)


def _sum_amount(user_id, tx_type, month=None):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            if month:
                cursor.execute(
                    """SELECT COALESCE(SUM(AMOUNT), 0)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?
                         AND DATE LIKE ?""",
                    (user_id, tx_type, f"{month}%"),
                )
            else:
                cursor.execute(
                    """SELECT COALESCE(SUM(AMOUNT), 0)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?""",
                    (user_id, tx_type),
                )
            return float(cursor.fetchone()[0])
    except sqlite3.Error:
        return 0.0


def get_username(user_id):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            return result["username"] if result else "Guest"
    except sqlite3.Error:
        return "User"


def get_category_totals(user_id, month=None, tx_type="expense"):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            if month:
                cursor.execute(
                    """SELECT CATEGORY, SUM(AMOUNT)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?
                         AND DATE LIKE ?
                       GROUP BY CATEGORY
                       ORDER BY SUM(AMOUNT) DESC""",
                    (user_id, tx_type, f"{month}%"),
                )
            else:
                cursor.execute(
                    """SELECT CATEGORY, SUM(AMOUNT)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?
                       GROUP BY CATEGORY
                       ORDER BY SUM(AMOUNT) DESC""",
                    (user_id, tx_type),
                )
            return cursor.fetchall()
    except sqlite3.Error:
        return []


def get_last_7_days_spending(user_id):
    date_7_days_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    filled = {}
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        filled[day] = 0.0
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT DATE, SUM(AMOUNT)
                   FROM expenses
                   WHERE USER_ID = ?
                     AND COALESCE(tx_type, 'expense') = 'expense'
                     AND DATE >= ?
                   GROUP BY DATE
                   ORDER BY DATE""",
                (user_id, date_7_days_ago),
            )
            for row in cursor.fetchall():
                filled[row[0]] = float(row[1])
            return list(filled.items())
    except sqlite3.Error:
        return list(filled.items())


def get_monthly_trend(user_id, months=6):
    """Return monthly expense totals for the last few months."""
    results = []
    today = datetime.now().replace(day=1)
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            for i in range(months - 1, -1, -1):
                year = today.year
                month = today.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                prefix = f"{year:04d}-{month:02d}"
                cursor.execute(
                    """SELECT COALESCE(SUM(AMOUNT), 0)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = 'expense'
                         AND DATE LIKE ?""",
                    (user_id, f"{prefix}%"),
                )
                results.append((prefix, float(cursor.fetchone()[0])))
        return results
    except sqlite3.Error:
        return results


def update_budget_limit(user_id, limit):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("UPDATE users SET budget_limit = ? WHERE id = ?", (limit, user_id))
            connection.commit()
            return True
    except sqlite3.Error:
        return False


def get_budget_limit(user_id):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT budget_limit FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            if result and result[0] is not None:
                return float(result[0])
            return 0.0
    except sqlite3.Error:
        return 0.0


def update_savings_goal(user_id, goal):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("UPDATE users SET savings_goal = ? WHERE id = ?", (goal, user_id))
            connection.commit()
            return True
    except sqlite3.Error:
        return False


def get_savings_goal(user_id):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT savings_goal FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            if result and result[0] is not None:
                return float(result[0])
            return 0.0
    except sqlite3.Error:
        return 0.0


def get_category_monthly_spend(user_id, category):
    current_month = datetime.now().strftime("%Y-%m")
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT COALESCE(SUM(AMOUNT), 0)
                   FROM expenses
                   WHERE USER_ID = ?
                     AND CATEGORY = ?
                     AND COALESCE(tx_type, 'expense') = 'expense'
                     AND DATE LIKE ?""",
                (user_id, category, f"{current_month}%"),
            )
            return float(cursor.fetchone()[0])
    except sqlite3.Error:
        return 0.0


def get_category_average(user_id, category):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT AVG(AMOUNT)
                   FROM expenses
                   WHERE USER_ID = ?
                     AND CATEGORY = ?
                     AND COALESCE(tx_type, 'expense') = 'expense'""",
                (user_id, category),
            )
            result = cursor.fetchone()[0]
            return float(result) if result is not None else 0.0
    except sqlite3.Error:
        return 0.0


def get_insights(user_id):
    """Build a small list of real insights from this user's own data."""
    month = datetime.now().strftime("%Y-%m")
    month_expense = total_expense(user_id, month)
    month_income = total_income(user_id, month)
    all_expense = total_expense(user_id)
    all_income = total_income(user_id)
    budget = get_budget_limit(user_id)
    goal = get_savings_goal(user_id)
    balance = all_income - all_expense
    month_balance = month_income - month_expense
    categories = get_category_totals(user_id, month)
    top_category = categories[0] if categories else None

    insights = []
    if month_expense == 0 and month_income == 0:
        insights.append("No transactions this month yet. Add income or an expense to see insights.")
    else:
        insights.append(
            f"This month you earned ₹{month_income:.2f} and spent ₹{month_expense:.2f} "
            f"(net ₹{month_balance:.2f})."
        )

    if top_category and month_expense > 0:
        share = (float(top_category[1]) / month_expense) * 100
        insights.append(
            f"Top category this month is {top_category[0]} "
            f"(₹{float(top_category[1]):.2f}, {share:.0f}% of spending)."
        )

    if budget > 0:
        remaining = budget - month_expense
        percent = (month_expense / budget) * 100
        if month_expense > budget:
            insights.append(
                f"Budget warning: monthly spending is ₹{month_expense:.2f}, "
                f"which is over your ₹{budget:.2f} limit ({percent:.0f}%)."
            )
        elif percent >= 80:
            insights.append(
                f"Budget warning: you have used {percent:.0f}% of your ₹{budget:.2f} monthly budget. "
                f"₹{remaining:.2f} left."
            )
        else:
            insights.append(
                f"Budget on track: ₹{remaining:.2f} remaining of ₹{budget:.2f} this month."
            )

    if goal > 0:
        if month_balance >= goal:
            insights.append(f"Savings goal met this month: net ₹{month_balance:.2f} vs goal ₹{goal:.2f}.")
        else:
            shortfall = goal - month_balance
            insights.append(
                f"Savings goal: you are ₹{shortfall:.2f} short of this month's ₹{goal:.2f} target."
            )

    if month_income > 0:
        save_rate = (month_balance / month_income) * 100
        insights.append(f"This month's saving rate is {save_rate:.0f}% of income.")

    return {
        "month": month,
        "month_expense": month_expense,
        "month_income": month_income,
        "month_balance": month_balance,
        "all_expense": all_expense,
        "all_income": all_income,
        "balance": balance,
        "budget": budget,
        "savings_goal": goal,
        "top_category": top_category[0] if top_category else None,
        "messages": insights,
        "categories": [(row[0], float(row[1])) for row in categories],
    }


def is_unusual_expense(user_id, category, amount):
    """Flag a spend that is much larger than this user's usual amount in the same category."""
    avg = get_category_average(user_id, category)
    if avg <= 0:
        return False, avg
    if amount >= avg * 2.5 and amount >= 500:
        return True, avg
    return False, avg


def delete_expense_with_history(expense_id, user_id):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT CATEGORY, AMOUNT, DATE,
                          COALESCE(description, '') AS description,
                          COALESCE(tx_type, 'expense') AS tx_type
                   FROM expenses WHERE id = ? AND USER_ID = ?""",
                (expense_id, user_id),
            )
            data = cursor.fetchone()
            if not data:
                return False

            deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """INSERT INTO delete_history
                   (USER_ID, CATEGORY, AMOUNT, EXPENSE_DATE, DELETED_AT, description, tx_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    data["CATEGORY"],
                    data["AMOUNT"],
                    data["DATE"],
                    deleted_at,
                    data["description"],
                    data["tx_type"],
                ),
            )
            cursor.execute(
                "DELETE FROM expenses WHERE id = ? AND USER_ID = ?",
                (expense_id, user_id),
            )
            connection.commit()
            return True
    except sqlite3.Error:
        return False


def view_delete_history(user_id):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT CATEGORY, AMOUNT, EXPENSE_DATE, DELETED_AT,
                          COALESCE(description, '') AS description,
                          COALESCE(tx_type, 'expense') AS tx_type
                   FROM delete_history
                   WHERE USER_ID = ?
                   ORDER BY DELETED_AT DESC""",
                (user_id,),
            )
            return cursor.fetchall()
    except sqlite3.Error:
        return []
