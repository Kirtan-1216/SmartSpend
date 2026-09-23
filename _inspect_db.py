import sqlite3

c = sqlite3.connect(r"d:\Desktop\SmartSpend\finance_tracker.db")
cur = c.cursor()
print("tables:", [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")])
for t in ["users", "expenses", "delete_history"]:
    print("---", t)
    print(list(cur.execute(f"PRAGMA table_info({t})")))
    print("count", cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone())
print("users:", cur.execute("SELECT id, username, budget_limit FROM users").fetchall())
print("expenses sample:", cur.execute("SELECT * FROM expenses LIMIT 20").fetchall())
print("history sample:", cur.execute("SELECT * FROM delete_history LIMIT 10").fetchall())
