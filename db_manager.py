import os
import sqlite3
import calendar
from contextlib import contextmanager
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_database_url():
    """Return sanitized PostgreSQL connection URL if configured in environment."""
    url = os.environ.get("DATABASE_URL")
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def is_postgres():
    return bool(get_database_url()) and HAS_PSYCOPG2


def get_db_path():
    """Dynamically resolve SQLite database path."""
    return os.path.abspath(os.environ.get("SMARTSPEND_DB") or os.path.join(BASE_DIR, "finance_tracker.db"))


# Backward-compatibility alias
DB_PATH = get_db_path()


def get_connection():
    """
    Establish a database connection.
    Uses PostgreSQL when DATABASE_URL is set, otherwise SQLite with WAL mode and foreign keys.
    """
    pg_url = get_database_url()
    if pg_url and HAS_PSYCOPG2:
        conn = psycopg2.connect(pg_url)
        return conn

    db_file = get_db_path()
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def get_db():
    """
    Context manager that guarantees transaction commits and connection closure.
    Prevents connection leaks and file-lock contention.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


class SmartRow(dict):
    """
    Universal dictionary row that supports:
    - Case-insensitive key lookup: row['CATEGORY'], row['category'], row['Category']
    - Tuple index lookup: row[0], row[1]
    - Attribute lookup: row.category, row.amount
    Ensures seamless compatibility between SQLite and PostgreSQL results.
    """
    def __init__(self, mapping=None, keys=None, values=None):
        super().__init__()
        self._keys = []
        self._values = []
        if mapping:
            for k, v in mapping.items():
                self[k] = v
                self._keys.append(k)
                self._values.append(v)
        elif keys is not None and values is not None:
            for k, v in zip(keys, values):
                self[k] = v
                self._keys.append(k)
                self._values.append(v)

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        if isinstance(item, str):
            if super().__contains__(item):
                return super().__getitem__(item)
            l = item.lower()
            if super().__contains__(l):
                return super().__getitem__(l)
            u = item.upper()
            if super().__contains__(u):
                return super().__getitem__(u)
        return super().__getitem__(item)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'SmartRow' has no attribute '{name}'")


def _adapt_sql(sql):
    """Translate SQLite parameter markers (?) to PostgreSQL (%s) when applicable."""
    if is_postgres():
        return sql.replace("?", "%s")
    return sql


def _execute(conn, sql, params=()):
    cursor = conn.cursor()
    cursor.execute(_adapt_sql(sql), params)
    return cursor


def _fetch_all_rows(cursor):
    if not cursor.description:
        return []
    keys = [d[0] for d in cursor.description]
    results = []
    for raw in cursor.fetchall():
        if hasattr(raw, "keys"):
            results.append(SmartRow(mapping=dict(raw)))
        else:
            results.append(SmartRow(keys=keys, values=list(raw)))
    return results


def _fetch_one_row(cursor):
    if not cursor.description:
        return None
    raw = cursor.fetchone()
    if raw is None:
        return None
    if hasattr(raw, "keys"):
        return SmartRow(mapping=dict(raw))
    keys = [d[0] for d in cursor.description]
    return SmartRow(keys=keys, values=list(raw))


def _add_column_if_missing(cursor, table, column, definition):
    if is_postgres():
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name = %s AND column_name = %s""",
            (table.lower(), column.lower()),
        )
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    else:
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError:
                # SQLite cannot add non-constant default (e.g. CURRENT_TIMESTAMP) in ALTER TABLE
                clean_def = definition.replace("DEFAULT CURRENT_TIMESTAMP", "").strip()
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {clean_def}")


def create_table():
    """Create database tables and apply backward-compatible schema updates."""
    with get_db() as connection:
        if is_postgres():
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                budget_limit REAL DEFAULT 0.0,
                savings_goal REAL DEFAULT 0.0)""",
            )
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                USER_ID INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                CATEGORY TEXT NOT NULL,
                AMOUNT REAL NOT NULL,
                DATE TEXT NOT NULL,
                description TEXT DEFAULT '',
                tx_type TEXT DEFAULT 'expense')""",
            )
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS delete_history (
                id SERIAL PRIMARY KEY,
                USER_ID INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                CATEGORY TEXT NOT NULL,
                AMOUNT REAL NOT NULL,
                EXPENSE_DATE TEXT NOT NULL,
                DELETED_AT TEXT NOT NULL,
                description TEXT DEFAULT '',
                tx_type TEXT DEFAULT 'expense')""",
            )
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS user_keywords (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                keyword TEXT NOT NULL,
                category TEXT NOT NULL,
                UNIQUE(user_id, keyword))""",
            )
        else:
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL)""",
            )
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                USER_ID INTEGER NOT NULL,
                CATEGORY TEXT NOT NULL,
                AMOUNT REAL NOT NULL,
                DATE TEXT NOT NULL,
                FOREIGN KEY (USER_ID) REFERENCES users (id) ON DELETE CASCADE)""",
            )
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS delete_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                USER_ID INTEGER NOT NULL,
                CATEGORY TEXT NOT NULL,
                AMOUNT REAL NOT NULL,
                EXPENSE_DATE TEXT NOT NULL,
                DELETED_AT TEXT NOT NULL,
                FOREIGN KEY (USER_ID) REFERENCES users (id) ON DELETE CASCADE)""",
            )
            _execute(
                connection,
                """CREATE TABLE IF NOT EXISTS user_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                category TEXT NOT NULL,
                UNIQUE(user_id, keyword),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE)""",
            )

        cursor = connection.cursor()
        _add_column_if_missing(cursor, "users", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        _add_column_if_missing(cursor, "users", "budget_limit", "REAL DEFAULT 0.0")
        _add_column_if_missing(cursor, "users", "savings_goal", "REAL DEFAULT 0.0")
        _add_column_if_missing(cursor, "expenses", "description", "TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "expenses", "tx_type", "TEXT DEFAULT 'expense'")
        _add_column_if_missing(cursor, "delete_history", "description", "TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "delete_history", "tx_type", "TEXT DEFAULT 'expense'")


def add_user(username, password):
    try:
        hashed_pw = generate_password_hash(password)
        with get_db() as connection:
            _execute(
                connection,
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_pw),
            )
            return True
    except Exception:
        return False


def check_user(username, password):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                "SELECT id, password FROM users WHERE username = ?",
                (username,),
            )
            result = _fetch_one_row(cursor)
            if result and check_password_hash(result["password"], password):
                return result["id"]
            return None
    except Exception:
        return None


def insert_expense(USER_ID, category, amount, date=None, description="", tx_type="expense"):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    tx_type = "income" if str(tx_type).lower() == "income" else "expense"
    description = (description or "").strip()
    try:
        with get_db() as connection:
            _execute(
                connection,
                """
                INSERT INTO expenses (USER_ID, CATEGORY, AMOUNT, DATE, description, tx_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (USER_ID, category.strip(), float(amount), date, description, tx_type),
            )
            return True
    except (ValueError, TypeError, Exception):
        return False


def delete_expense(expense_id, user_id):
    """Delete an expense strictly scoped to the authenticated user."""
    if not user_id:
        return False
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                "DELETE FROM expenses WHERE id = ? AND USER_ID = ?",
                (expense_id, user_id),
            )
            return cursor.rowcount > 0
    except Exception:
        return False


def view_expenses(USER_ID, tx_type=None):
    try:
        with get_db() as connection:
            if tx_type:
                cursor = _execute(
                    connection,
                    """SELECT id, USER_ID, CATEGORY, AMOUNT, DATE,
                              COALESCE(description, '') AS description,
                              COALESCE(tx_type, 'expense') AS tx_type
                       FROM expenses
                       WHERE USER_ID = ? AND COALESCE(tx_type, 'expense') = ?
                       ORDER BY DATE DESC, id DESC""",
                    (USER_ID, tx_type),
                )
            else:
                cursor = _execute(
                    connection,
                    """SELECT id, USER_ID, CATEGORY, AMOUNT, DATE,
                              COALESCE(description, '') AS description,
                              COALESCE(tx_type, 'expense') AS tx_type
                       FROM expenses
                       WHERE USER_ID = ?
                       ORDER BY DATE DESC, id DESC""",
                    (USER_ID,),
                )
            return _fetch_all_rows(cursor)
    except Exception:
        return []


def get_expense(expense_id, user_id):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """SELECT id, USER_ID, CATEGORY, AMOUNT, DATE,
                          COALESCE(description, '') AS description,
                          COALESCE(tx_type, 'expense') AS tx_type
                   FROM expenses WHERE id = ? AND USER_ID = ?""",
                (expense_id, user_id),
            )
            return _fetch_one_row(cursor)
    except Exception:
        return None


def update_expense(expense_id, user_id, category, amount, date, description="", tx_type="expense"):
    tx_type = "income" if str(tx_type).lower() == "income" else "expense"
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """UPDATE expenses
                   SET CATEGORY = ?, AMOUNT = ?, DATE = ?, description = ?, tx_type = ?
                   WHERE id = ? AND USER_ID = ?""",
                (category.strip(), float(amount), date, (description or "").strip(), tx_type, expense_id, user_id),
            )
            return cursor.rowcount == 1
    except (ValueError, TypeError, Exception):
        return False


def total_expense(USER_ID, month=None):
    return _sum_amount(USER_ID, "expense", month)


def total_income(USER_ID, month=None):
    return _sum_amount(USER_ID, "income", month)


def _sum_amount(user_id, tx_type, month=None):
    try:
        with get_db() as connection:
            if month:
                cursor = _execute(
                    connection,
                    """SELECT COALESCE(SUM(AMOUNT), 0)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?
                         AND DATE LIKE ?""",
                    (user_id, tx_type, f"{month}%"),
                )
            else:
                cursor = _execute(
                    connection,
                    """SELECT COALESCE(SUM(AMOUNT), 0)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?""",
                    (user_id, tx_type),
                )
            row = cursor.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return 0.0


def get_username(user_id):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                "SELECT username FROM users WHERE id = ?",
                (user_id,),
            )
            result = _fetch_one_row(cursor)
            return result["username"] if result else "Guest"
    except Exception:
        return "User"


def get_category_totals(user_id, month=None, tx_type="expense"):
    """Return list of (category, total_amount) tuples sorted descending."""
    try:
        with get_db() as connection:
            if month:
                cursor = _execute(
                    connection,
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
                cursor = _execute(
                    connection,
                    """SELECT CATEGORY, SUM(AMOUNT)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = ?
                       GROUP BY CATEGORY
                       ORDER BY SUM(AMOUNT) DESC""",
                    (user_id, tx_type),
                )
            return [(row[0], float(row[1])) for row in cursor.fetchall()]
    except Exception:
        return []


def get_last_7_days_spending(user_id):
    """Return daily expense totals for the past 7 days."""
    date_7_days_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    filled = {}
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        filled[day] = 0.0
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
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
    except Exception:
        return list(filled.items())


def get_monthly_trend(user_id, months=6):
    """Return monthly expense totals for the last few months."""
    results = []
    today = datetime.now().replace(day=1)
    try:
        with get_db() as connection:
            for i in range(months - 1, -1, -1):
                year = today.year
                month = today.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                prefix = f"{year:04d}-{month:02d}"
                cursor = _execute(
                    connection,
                    """SELECT COALESCE(SUM(AMOUNT), 0)
                       FROM expenses
                       WHERE USER_ID = ?
                         AND COALESCE(tx_type, 'expense') = 'expense'
                         AND DATE LIKE ?""",
                    (user_id, f"{prefix}%"),
                )
                val = cursor.fetchone()[0]
                results.append((prefix, float(val) if val is not None else 0.0))
        return results
    except Exception:
        return results


def update_budget_limit(user_id, limit):
    try:
        with get_db() as connection:
            _execute(
                connection,
                "UPDATE users SET budget_limit = ? WHERE id = ?",
                (limit, user_id),
            )
            return True
    except Exception:
        return False


def get_budget_limit(user_id):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                "SELECT budget_limit FROM users WHERE id = ?",
                (user_id,),
            )
            result = cursor.fetchone()
            if result and result[0] is not None:
                return float(result[0])
            return 0.0
    except Exception:
        return 0.0


def update_savings_goal(user_id, goal):
    try:
        with get_db() as connection:
            _execute(
                connection,
                "UPDATE users SET savings_goal = ? WHERE id = ?",
                (goal, user_id),
            )
            return True
    except Exception:
        return False


def get_savings_goal(user_id):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                "SELECT savings_goal FROM users WHERE id = ?",
                (user_id,),
            )
            result = cursor.fetchone()
            if result and result[0] is not None:
                return float(result[0])
            return 0.0
    except Exception:
        return 0.0


def get_category_monthly_spend(user_id, category):
    current_month = datetime.now().strftime("%Y-%m")
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """SELECT COALESCE(SUM(AMOUNT), 0)
                   FROM expenses
                   WHERE USER_ID = ?
                     AND CATEGORY = ?
                     AND COALESCE(tx_type, 'expense') = 'expense'
                     AND DATE LIKE ?""",
                (user_id, category, f"{current_month}%"),
            )
            val = cursor.fetchone()[0]
            return float(val) if val is not None else 0.0
    except Exception:
        return 0.0


def get_category_average(user_id, category):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """SELECT AVG(AMOUNT)
                   FROM expenses
                   WHERE USER_ID = ?
                     AND CATEGORY = ?
                     AND COALESCE(tx_type, 'expense') = 'expense'""",
                (user_id, category),
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                return float(row[0])
            return 0.0
    except Exception:
        return 0.0


def is_unusual_expense(user_id, category, amount):
    """Flag a spend that is significantly larger than this user's category baseline."""
    avg = get_category_average(user_id, category)
    if avg <= 0:
        return False, avg
    if amount >= avg * 2.5 and amount >= 500:
        return True, avg
    return False, avg


def get_unusual_expenses(user_id, limit=5):
    """
    Retrieve recently added expenses that deviated significantly from normal category averages.
    Explainable statistical method: >= 2.5x historical category average and >= ₹500.
    """
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """SELECT CATEGORY, AVG(AMOUNT)
                   FROM expenses
                   WHERE USER_ID = ? AND COALESCE(tx_type, 'expense') = 'expense'
                   GROUP BY CATEGORY""",
                (user_id,),
            )
            cat_avgs = {row[0]: float(row[1]) for row in cursor.fetchall()}

            cursor = _execute(
                connection,
                """SELECT id, CATEGORY, AMOUNT, DATE, description
                   FROM expenses
                   WHERE USER_ID = ? AND COALESCE(tx_type, 'expense') = 'expense'
                   ORDER BY DATE DESC, id DESC
                   LIMIT 50""",
                (user_id,),
            )
            unusual = []
            for row in _fetch_all_rows(cursor):
                cat = row["CATEGORY"]
                amt = float(row["AMOUNT"])
                avg = cat_avgs.get(cat, 0.0)
                if avg > 0 and amt >= avg * 2.5 and amt >= 500:
                    unusual.append({
                        "id": row["id"],
                        "category": cat,
                        "amount": amt,
                        "date": row["DATE"],
                        "description": row["description"] or cat,
                        "category_avg": avg,
                        "multiple": round(amt / avg, 1),
                    })
                    if len(unusual) >= limit:
                        break
            return unusual
    except Exception:
        return []


def calculate_financial_health_score(income, expense, budget, tx_count):
    """
    Compute an explainable Financial Health Score (0-100) based on 4 pillars:
    1. Cash Flow (25 pts): Positive net balance (+25), break-even (+15), deficit (0)
    2. Savings Rate (35 pts): >=25% (+35), >=15% (+25), >=5% (+15), >0% (+5)
    3. Budget Discipline (25 pts): <=80% budget (+25), <=100% (+15), exceeded (0), no budget (+15 baseline)
    4. Tracking Consistency (15 pts): >=5 transactions (+15), 1-4 (+10), 0 (+5)
    """
    score = 0
    net = income - expense

    # 1. Cash flow pillar
    if net > 0:
        score += 25
    elif net == 0 and income > 0:
        score += 15

    # 2. Savings rate pillar
    rate = (net / income * 100) if income > 0 else 0.0
    if rate >= 25:
        score += 35
    elif rate >= 15:
        score += 25
    elif rate >= 5:
        score += 15
    elif rate > 0:
        score += 5

    # 3. Budget discipline pillar
    if budget > 0:
        used = (expense / budget) * 100
        if used <= 80:
            score += 25
        elif used <= 100:
            score += 15
    else:
        score += 15

    # 4. Consistency pillar
    if tx_count >= 5:
        score += 15
    elif tx_count >= 1:
        score += 10
    else:
        score += 5

    final_score = min(100, max(0, score))
    if final_score >= 85:
        grade = "A+ Excellent"
        status_class = "excellent"
    elif final_score >= 70:
        grade = "B+ Healthy"
        status_class = "good"
    elif final_score >= 50:
        grade = "C Fair"
        status_class = "fair"
    else:
        grade = "Needs Attention"
        status_class = "warning"

    return final_score, grade, status_class


def get_insights(user_id):
    """
    Smart Financial Copilot / Command Center intelligence engine.
    Generates explainable insights, alerts, suggestions, and financial health snapshot.
    """
    now = datetime.now()
    month = now.strftime("%Y-%m")
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

    # Count current month transactions
    with get_db() as connection:
        cursor = _execute(
            connection,
            "SELECT COUNT(*) FROM expenses WHERE USER_ID = ? AND DATE LIKE ?",
            (user_id, f"{month}%"),
        )
        tx_count = cursor.fetchone()[0]

        # Find largest single transaction this month
        cursor = _execute(
            connection,
            """SELECT CATEGORY, AMOUNT, description
               FROM expenses
               WHERE USER_ID = ? AND COALESCE(tx_type, 'expense') = 'expense' AND DATE LIKE ?
               ORDER BY AMOUNT DESC LIMIT 1""",
            (user_id, f"{month}%"),
        )
        top_tx_row = _fetch_one_row(cursor)
        largest_expense = (
            {"category": top_tx_row["CATEGORY"], "amount": float(top_tx_row["AMOUNT"]), "description": top_tx_row["description"]}
            if top_tx_row else None
        )

    # Previous month comparison
    prev_month_date = now.replace(day=1) - timedelta(days=1)
    prev_month = prev_month_date.strftime("%Y-%m")
    prev_month_expense = total_expense(user_id, prev_month)
    mom_change_percent = None
    if prev_month_expense > 0:
        mom_change_percent = round(((month_expense - prev_month_expense) / prev_month_expense) * 100, 1)

    # Daily average spending
    days_elapsed = max(1, now.day)
    daily_average = round(month_expense / days_elapsed, 2)

    # Budget metrics
    budget_used_percent = round((month_expense / budget) * 100, 1) if budget > 0 else 0.0
    budget_remaining = round(budget - month_expense, 2) if budget > 0 else 0.0
    if budget <= 0:
        budget_status = "none"
    elif month_expense > budget:
        budget_status = "exceeded"
    elif budget_used_percent >= 80:
        budget_status = "warning"
    else:
        budget_status = "good"

    # Daily budget left for remainder of month
    _, total_days_in_month = calendar.monthrange(now.year, now.month)
    days_remaining = max(1, total_days_in_month - now.day)
    daily_budget_remaining = (
        round(max(0.0, budget_remaining) / days_remaining, 2)
        if (budget > 0 and budget_remaining > 0) else None
    )

    # Savings rate
    savings_rate = round((month_balance / month_income) * 100, 1) if month_income > 0 else 0.0

    # Financial Health Score
    health_score, health_grade, health_status_class = calculate_financial_health_score(
        month_income, month_expense, budget, tx_count
    )

    # Explainable Smart Alerts
    smart_alerts = []
    if budget > 0:
        if month_expense > budget:
            over = month_expense - budget
            smart_alerts.append({
                "type": "danger",
                "title": "Budget Exceeded",
                "message": f"Monthly spending of ₹{month_expense:,.2f} has surpassed your ₹{budget:,.2f} limit by ₹{over:,.2f}.",
            })
        elif budget_used_percent >= 80:
            smart_alerts.append({
                "type": "warning",
                "title": "Budget Alert",
                "message": f"You have used {budget_used_percent:.0f}% of your monthly limit. ₹{budget_remaining:,.2f} remains.",
            })

    if mom_change_percent is not None:
        if mom_change_percent > 20:
            smart_alerts.append({
                "type": "warning",
                "title": "Spending Spike",
                "message": f"Your spending is {mom_change_percent:.0f}% higher compared to the same point last month.",
            })
        elif mom_change_percent < -15:
            smart_alerts.append({
                "type": "success",
                "title": "Spending Reduced",
                "message": f"Great progress! You are spending {abs(mom_change_percent):.0f}% less than last month.",
            })

    if top_category and month_expense > 0:
        share = (float(top_category[1]) / month_expense) * 100
        if share >= 40:
            smart_alerts.append({
                "type": "info",
                "title": "Category Concentration",
                "message": f"{top_category[0]} accounts for {share:.0f}% (₹{float(top_category[1]):,.2f}) of your total expenses this month.",
            })

    # Actionable Saving Suggestions based on actual data
    suggestions = []
    # 1. Discretionary trim suggestion
    discretionary = ["Food", "Entertainment", "Shopping", "Miscellaneous"]
    disc_spends = [cat for cat in categories if cat[0] in discretionary and float(cat[1]) >= 800]
    if disc_spends:
        target_cat = disc_spends[0]
        amt = float(target_cat[1])
        savings_10 = round(amt * 0.10, 2)
        suggestions.append({
            "title": f"Trim 10% on {target_cat[0]}",
            "message": f"You spent ₹{amt:,.2f} on {target_cat[0]} this month. Reducing non-essential purchases here could save ~₹{savings_10:,.2f}.",
            "impact": f"+₹{savings_10:,.2f}/mo",
        })

    # 2. Daily pacing suggestion
    if daily_budget_remaining is not None:
        suggestions.append({
            "title": "Pace Daily Spending",
            "message": f"Keep expenses under ₹{daily_budget_remaining:,.2f}/day for the remaining {days_remaining} days to finish the month strictly within budget.",
            "impact": f"Target: ₹{daily_budget_remaining:,.2f}/day",
        })

    # 3. 20% Emergency Fund Benchmark
    if month_income > 0:
        ideal_save = round(month_income * 0.20, 2)
        if month_balance < ideal_save:
            gap = round(ideal_save - month_balance, 2)
            suggestions.append({
                "title": "Build 20% Safety Reserve",
                "message": f"Saving 20% (₹{ideal_save:,.2f}) creates a reliable emergency fund. You are currently ₹{gap:,.2f} away from this benchmark.",
                "impact": f"Target: ₹{ideal_save:,.2f}",
            })
        else:
            suggestions.append({
                "title": "Excellent Wealth Accumulation",
                "message": f"You are saving {savings_rate:.0f}% of your income, beating the 20% financial rule of thumb!",
                "impact": "Top Tier",
            })

    # Legacy natural language messages
    insights_messages = []
    if month_expense == 0 and month_income == 0:
        insights_messages.append("No transactions this month yet. Add income or an expense to see insights.")
    else:
        insights_messages.append(
            f"This month you earned ₹{month_income:,.2f} and spent ₹{month_expense:,.2f} "
            f"(net ₹{month_balance:,.2f})."
        )

    if top_category and month_expense > 0:
        share = (float(top_category[1]) / month_expense) * 100
        insights_messages.append(
            f"Top category this month is {top_category[0]} "
            f"(₹{float(top_category[1]):,.2f}, {share:.0f}% of spending)."
        )

    if budget > 0:
        if month_expense > budget:
            insights_messages.append(
                f"Budget warning: monthly spending is ₹{month_expense:,.2f}, "
                f"which is over your ₹{budget:,.2f} limit ({budget_used_percent:.0f}%)."
            )
        elif budget_used_percent >= 80:
            insights_messages.append(
                f"Budget warning: you have used {budget_used_percent:.0f}% of your ₹{budget:,.2f} monthly budget. "
                f"₹{budget_remaining:,.2f} left."
            )
        else:
            insights_messages.append(
                f"Budget on track: ₹{budget_remaining:,.2f} remaining of ₹{budget:,.2f} this month."
            )

    if goal > 0:
        if month_balance >= goal:
            insights_messages.append(f"Savings goal met this month: net ₹{month_balance:,.2f} vs goal ₹{goal:,.2f}.")
        else:
            shortfall = goal - month_balance
            insights_messages.append(
                f"Savings goal: you are ₹{shortfall:,.2f} short of this month's ₹{goal:,.2f} target."
            )

    if month_income > 0:
        insights_messages.append(f"This month's saving rate is {savings_rate:.0f}% of income.")

    # Recent unusual transactions
    unusual_expenses = get_unusual_expenses(user_id, limit=4)

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
        "messages": insights_messages,
        "categories": [(row[0], float(row[1])) for row in categories],
        # Smart Copilot enhancements:
        "health_score": health_score,
        "health_grade": health_grade,
        "health_status_class": health_status_class,
        "daily_average": daily_average,
        "mom_change_percent": mom_change_percent,
        "prev_month_expense": prev_month_expense,
        "prev_month": prev_month,
        "savings_rate": savings_rate,
        "budget_used_percent": budget_used_percent,
        "budget_remaining": budget_remaining,
        "budget_status": budget_status,
        "daily_budget_remaining": daily_budget_remaining,
        "largest_expense": largest_expense,
        "unusual_expenses": unusual_expenses,
        "smart_alerts": smart_alerts,
        "suggestions": suggestions,
        "tx_count": tx_count,
    }


def delete_expense_with_history(expense_id, user_id):
    """Safely archive and delete an expense belonging to user_id."""
    if not user_id:
        return False
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """SELECT CATEGORY, AMOUNT, DATE,
                          COALESCE(description, '') AS description,
                          COALESCE(tx_type, 'expense') AS tx_type
                   FROM expenses WHERE id = ? AND USER_ID = ?""",
                (expense_id, user_id),
            )
            data = _fetch_one_row(cursor)
            if not data:
                return False

            deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _execute(
                connection,
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
            _execute(
                connection,
                "DELETE FROM expenses WHERE id = ? AND USER_ID = ?",
                (expense_id, user_id),
            )
            return True
    except Exception:
        return False


def view_delete_history(user_id):
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                """SELECT CATEGORY, AMOUNT, EXPENSE_DATE, DELETED_AT,
                          COALESCE(description, '') AS description,
                          COALESCE(tx_type, 'expense') AS tx_type
                   FROM delete_history
                   WHERE USER_ID = ?
                   ORDER BY DELETED_AT DESC""",
                (user_id,),
            )
            return _fetch_all_rows(cursor)
    except Exception:
        return []


def save_user_keyword(user_id, keyword, category):
    kw = (keyword or "").strip().lower()
    cat = (category or "").strip()
    if not kw or not cat or not user_id:
        return False
    try:
        with get_db() as connection:
            _execute(
                connection,
                """INSERT INTO user_keywords (user_id, keyword, category)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, keyword) DO UPDATE SET category = excluded.category""",
                (user_id, kw, cat),
            )
            return True
    except Exception:
        return False


def get_user_keywords(user_id):
    if not user_id:
        return {}
    try:
        with get_db() as connection:
            cursor = _execute(
                connection,
                "SELECT keyword, category FROM user_keywords WHERE user_id = ?",
                (user_id,),
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception:
        return {}
