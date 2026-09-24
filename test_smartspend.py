import os
import tempfile
import unittest
from datetime import datetime, timedelta


def _prepare_env():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.environ["SMARTSPEND_DB"] = path
    os.environ["SECRET_KEY"] = "unit-test-secret-key-12345"
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

    def test_named_month_with_year(self):
        parsed = process_natural_language("Paid ₹800 on 15th August 2026 for dinner")
        self.assertEqual(parsed["amount"], 800.0)
        self.assertEqual(parsed["date"], "2026-08-15")
        self.assertEqual(parsed["category"], "Food")

    def test_multipliers_k_and_thousand(self):
        p1 = process_natural_language("Spent 5k on shopping")
        self.assertEqual(p1["amount"], 5000.0)
        self.assertEqual(p1["category"], "Shopping")

        p2 = process_natural_language("Spent 2.5k on food")
        self.assertEqual(p2["amount"], 2500.0)
        self.assertEqual(p2["category"], "Food")

        p3 = process_natural_language("Paid 5 thousand for rent")
        self.assertEqual(p3["amount"], 5000.0)
        self.assertEqual(p3["category"], "Utilities")

    def test_multipliers_lakh_and_lac(self):
        p1 = process_natural_language("Spent 5 lakh on a car")
        self.assertEqual(p1["amount"], 500000.0)
        self.assertEqual(p1["category"], "Transport")

        p2 = process_natural_language("Spent 5 lac on a car")
        self.assertEqual(p2["amount"], 500000.0)

        p3 = process_natural_language("Spent 5 lacs on a car")
        self.assertEqual(p3["amount"], 500000.0)

        p4 = process_natural_language("Spent 2.5 lakh on a car")
        self.assertEqual(p4["amount"], 250000.0)
        self.assertEqual(p4["category"], "Transport")

    def test_multipliers_crore_and_cr(self):
        p1 = process_natural_language("Spent 1 crore on property")
        self.assertEqual(p1["amount"], 10000000.0)
        self.assertEqual(p1["category"], "Investment")

        p2 = process_natural_language("Spent 2.5 cr on property")
        self.assertEqual(p2["amount"], 25000000.0)
        self.assertEqual(p2["category"], "Investment")

    def test_currency_suffixes_and_formats(self):
        self.assertEqual(process_natural_language("Bought groceries for 1,200 rupees")["amount"], 1200.0)
        self.assertEqual(process_natural_language("500 rupees")["amount"], 500.0)
        self.assertEqual(process_natural_language("Rs 500")["amount"], 500.0)
        self.assertEqual(process_natural_language("Rs. 500")["amount"], 500.0)
        self.assertEqual(process_natural_language("500 INR")["amount"], 500.0)
        self.assertEqual(process_natural_language("₹500")["amount"], 500.0)

    def test_domain_categories(self):
        self.assertEqual(process_natural_language("Bought tractor for 5000")["category"], "Agriculture")
        self.assertEqual(process_natural_language("Pooja at temple 100")["category"], "Spiritual & Religious")
        self.assertEqual(process_natural_language("Bought cricket bat for 1200")["category"], "Sports & Fitness")
        self.assertEqual(process_natural_language("Bought motor and bearing for 3500")["category"], "Industrial")


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

    def test_user_keyword_learning_and_nlp_prediction(self):
        self.signup("keyword_user")
        user_id = db_manager.check_user("keyword_user", "secret123")

        parsed_before = process_natural_language("Bought zxcvitem for 500", user_id=user_id)
        self.assertEqual(parsed_before["category"], "Miscellaneous")

        self.client.post(
            "/add",
            data={
                "category": "Entertainment",
                "amount": "500",
                "tx_type": "expense",
                "date": "2026-09-23",
                "description": "Bought zxcvitem for fun",
            },
            follow_redirects=True,
        )

        kws = db_manager.get_user_keywords(user_id)
        self.assertIn("zxcvitem", kws)
        self.assertEqual(kws["zxcvitem"], "Entertainment")

        parsed_after = process_natural_language("Spent 200 on zxcvitem today", user_id=user_id)
        self.assertEqual(parsed_after["category"], "Entertainment")

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

    def test_database_persistence_across_connection_reopen(self):
        """
        Step-by-step verification requested for Phase 2:
        1. Register test user
        2. Close/reopen connection
        3. Attempt login
        4. Add expense
        5. Close/reopen connection
        6. Verify expense remains
        7. Verify dashboard sees expense
        """
        # 1. Register test user
        self.signup("persist_user", "securePass123")
        self.client.get("/logout", follow_redirects=True)

        # 2. Simulate fresh connection/reopen
        with db_manager.get_db() as conn:
            pass

        # 3. Attempt login again
        login_res = self.client.post(
            "/login",
            data={"username": "persist_user", "password": "securePass123"},
            follow_redirects=True,
        )
        self.assertIn(b"Logged in successfully", login_res.data)

        # 4. Add expense
        add_res = self.client.post(
            "/add",
            data={
                "category": "Utilities",
                "amount": "1450.00",
                "tx_type": "expense",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": "Electricity Bill",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Electricity Bill", add_res.data)

        # 5. Simulate closing and reopening database connection
        with db_manager.get_db() as conn:
            cursor = db_manager._execute(conn, "SELECT COUNT(*) FROM expenses")
            count = cursor.fetchone()[0]
            self.assertGreaterEqual(count, 1)

        # 6. Verify expense remains in database
        uid = db_manager.check_user("persist_user", "securePass123")
        rows = db_manager.view_expenses(uid)
        descriptions = [r["description"] for r in rows]
        self.assertIn("Electricity Bill", descriptions)

        # 7. Verify dashboard still sees the expense
        dash = self.client.get("/")
        self.assertIn(b"Electricity Bill", dash.data)
        self.assertIn(b"1450.00", dash.data)

    def test_financial_copilot_intelligence(self):
        self.signup("copilot_user")
        uid = db_manager.check_user("copilot_user", "secret123")

        # Set budget and goal
        self.client.post(
            "/settings",
            data={"budget_limit": "10000", "savings_goal": "5000"},
            follow_redirects=True,
        )

        # Add income and expense
        self.client.post(
            "/add",
            data={"category": "Salary", "amount": "40000", "tx_type": "income", "date": datetime.now().strftime("%Y-%m-%d")},
            follow_redirects=True,
        )
        self.client.post(
            "/add",
            data={"category": "Food", "amount": "2000", "tx_type": "expense", "date": datetime.now().strftime("%Y-%m-%d")},
            follow_redirects=True,
        )

        insights = db_manager.get_insights(uid)
        self.assertEqual(insights["month_income"], 40000.0)
        self.assertEqual(insights["month_expense"], 2000.0)
        self.assertEqual(insights["month_balance"], 38000.0)
        self.assertGreaterEqual(insights["health_score"], 80)
        self.assertIn("A+ Excellent", insights["health_grade"])

        # Test Copilot API
        api_res = self.client.get("/api/copilot")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.get_json()
        self.assertEqual(data["month_income"], 40000.0)

    def test_smart_add(self):
        self.signup("gina")
        response = self.client.post(
            "/smart_add",
            data={"smart_input": "Paid 120 for Uber today"},
            follow_redirects=True,
        )
        self.assertIn(b"Smart added", response.data)
        self.assertIn(b"Transport", response.data)

    def test_unauthorized_api(self):
        response = self.client.get("/api/data")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
