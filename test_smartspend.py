import os
import tempfile
import unittest
from datetime import datetime, timedelta


def _prepare_env():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.environ["SMARTSPEND_DB"] = path
    os.environ["SECRET_KEY"] = "unit-test-secret-key"
    os.environ["FLASK_DEBUG"] = "0"
    return path


DB_PATH = _prepare_env()

from app import app  # noqa: E402
import db_manager  # noqa: E402
from nlp_utils import process_natural_language  # noqa: E402


class NlpTests(unittest.TestCase):
    def test_dinner_yesterday(self):
        parsed = process_natural_language("Spent ₹500 on dinner yesterday")
        yesterday = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(parsed["amount"], 500.0)
        self.assertEqual(parsed["category"], "Food")
        self.assertEqual(parsed["tx_type"], "expense")
        self.assertEqual(parsed["date"], yesterday)

    def test_uber_today(self):
        parsed = process_natural_language("Paid 120 for Uber today")
        self.assertEqual(parsed["amount"], 120.0)
        self.assertEqual(parsed["category"], "Transport")
        self.assertEqual(parsed["date"], datetime.now().strftime("%Y-%m-%d"))

    def test_groceries(self):
        parsed = process_natural_language("Bought groceries for 850")
        self.assertEqual(parsed["amount"], 850.0)
        self.assertEqual(parsed["category"], "Food")

    def test_salary_income(self):
        parsed = process_natural_language("Received salary 25000")
        self.assertEqual(parsed["amount"], 25000.0)
        self.assertEqual(parsed["tx_type"], "income")
        self.assertEqual(parsed["category"], "Salary")

    def test_date_not_treated_as_amount(self):
        parsed = process_natural_language("Spent 400 on coffee on 21/04/2026")
        self.assertEqual(parsed["amount"], 400.0)
        self.assertEqual(parsed["date"], "2026-04-21")


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def signup(self, username, password="secret123"):
        return self.client.post(
            "/signup",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def test_register_login_logout(self):
        response = self.signup("alice")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account created successfully", response.data)
        self.assertIn(b"Welcome", response.data)

        logout = self.client.get("/logout", follow_redirects=True)
        self.assertIn(b"You have been logged out", logout.data)

        bad = self.client.post(
            "/login",
            data={"username": "alice", "password": "wrong-password"},
            follow_redirects=True,
        )
        self.assertIn(b"Invalid username or password", bad.data)

        good = self.client.post(
            "/login",
            data={"username": "alice", "password": "secret123"},
            follow_redirects=True,
        )
        self.assertIn(b"Logged in successfully", good.data)

    def test_short_password_rejected(self):
        response = self.signup("tinyuser", "123")
        self.assertIn(b"Password must be at least 6 characters", response.data)

    def test_add_edit_delete_expense_and_income(self):
        self.signup("bob")
        added = self.client.post(
            "/add",
            data={
                "category": "Food",
                "amount": "99.50",
                "tx_type": "expense",
                "date": "2026-09-21",
                "description": "Lunch",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Expense added successfully", added.data)
        self.assertIn(b"Lunch", added.data)
        self.assertIn(b"99.50", added.data)

        income = self.client.post(
            "/add",
            data={
                "category": "Salary",
                "amount": "1000",
                "tx_type": "income",
                "date": "2026-09-21",
                "description": "Pay",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Income added successfully", income.data)

        dashboard = self.client.get("/")
        self.assertIn(b"1000.00", dashboard.data)

        expenses = db_manager.view_expenses(db_manager.check_user("bob", "secret123"))
        expense_row = [row for row in expenses if row["tx_type"] == "expense"][0]
        edited = self.client.post(
            f"/edit/{expense_row['id']}",
            data={
                "category": "Food",
                "amount": "120.00",
                "tx_type": "expense",
                "date": "2026-09-21",
                "description": "Lunch updated",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Transaction updated successfully", edited.data)
        self.assertIn(b"Lunch updated", edited.data)

        deleted = self.client.post(f"/delete/{expense_row['id']}", follow_redirects=True)
        self.assertIn(b"Transaction deleted successfully", deleted.data)
        history = self.client.get("/history")
        self.assertIn(b"Lunch updated", history.data)

    def test_invalid_amount(self):
        self.signup("carol")
        response = self.client.post(
            "/add",
            data={"category": "Food", "amount": "-10", "tx_type": "expense"},
            follow_redirects=True,
        )
        self.assertIn(b"Please enter a valid amount", response.data)

    def test_user_data_isolation(self):
        self.signup("dave")
        self.client.post(
            "/add",
            data={"category": "Secret", "amount": "42", "tx_type": "expense"},
            follow_redirects=True,
        )
        dave_id = db_manager.check_user("dave", "secret123")
        dave_rows = db_manager.view_expenses(dave_id)
        secret_id = dave_rows[0]["id"]

        self.client.get("/logout", follow_redirects=True)
        self.signup("erin")
        other_dashboard = self.client.get("/")
        self.assertNotIn(b"Secret", other_dashboard.data)

        steal = self.client.post(f"/delete/{secret_id}", follow_redirects=True)
        self.assertIn(b"Failed to delete transaction", steal.data)
        self.assertTrue(db_manager.get_expense(secret_id, dave_id))

    def test_persistence_and_dashboard_totals(self):
        self.signup("frank")
        self.client.post(
            "/add",
            data={"category": "Food", "amount": "200", "tx_type": "expense", "date": datetime.now().strftime("%Y-%m-%d")},
            follow_redirects=True,
        )
        self.client.post(
            "/add",
            data={"category": "Salary", "amount": "1000", "tx_type": "income", "date": datetime.now().strftime("%Y-%m-%d")},
            follow_redirects=True,
        )
        user_id = db_manager.check_user("frank", "secret123")
        self.assertEqual(db_manager.total_expense(user_id), 200.0)
        self.assertEqual(db_manager.total_income(user_id), 1000.0)
        insights = db_manager.get_insights(user_id)
        self.assertEqual(insights["balance"], 800.0)

        self.client.get("/logout", follow_redirects=True)
        again = self.client.post(
            "/login",
            data={"username": "frank", "password": "secret123"},
            follow_redirects=True,
        )
        self.assertIn(b"Food", again.data)
        self.assertIn(b"200.00", again.data)

    def test_smart_add(self):
        self.signup("gina")
        response = self.client.post(
            "/smart_add",
            data={"smart_input": "Paid 120 for Uber today"},
            follow_redirects=True,
        )
        self.assertIn(b"Smart added", response.data)
        self.assertIn(b"Transport", response.data)

    def test_duplicate_username(self):
        self.signup("hank")
        self.client.get("/logout", follow_redirects=True)
        again = self.signup("hank")
        self.assertIn(b"Username already taken", again.data)

    def test_unauthorized_api(self):
        response = self.client.get("/api/data")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
