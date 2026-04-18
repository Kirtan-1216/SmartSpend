import sqlite3
from datetime import datetime

# 1. INITIALIZE DATABASE TABLES
def create_table():
    with sqlite3.connect("finance_tracker.db") as connection:
        cursor = connection.cursor()
        # Table to store user credentials
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL)''')
        
        # Table to store expenses, linked to a specific USER_ID
        cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            USER_ID INTEGER NOT NULL,
            CATEGORY TEXT NOT NULL,
            AMOUNT REAL NOT NULL,
            DATE TEXT NOT NULL,
            FOREIGN KEY (USER_ID) REFERENCES users (id))''')
        
        # NEW: History table to track deletions
        cursor.execute('''CREATE TABLE IF NOT EXISTS delete_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            USER_ID INTEGER NOT NULL,
            CATEGORY TEXT NOT NULL,
            AMOUNT REAL NOT NULL,
            EXPENSE_DATE TEXT NOT NULL,
            DELETED_AT TEXT NOT NULL,
            FOREIGN KEY (USER_ID) REFERENCES users (id))''')
        

        connection.commit()
        print("DEBUG: Database Tables Created Successfully")

# 2. USER AUTHENTICATION FUNCTIONS
from werkzeug.security import generate_password_hash, check_password_hash

def add_user(username, password):
    try:
        hashed_pw = generate_password_hash(password)
        with sqlite3.connect("finance_tracker.db") as connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
            connection.commit()
            print(f"DEBUG: User '{username}' added successfully!")
            return True
    except sqlite3.IntegrityError:
        print(f"DEBUG: Signup Error: Username '{username}' already exists.")
        return False
    except sqlite3.Error as e:
        print(f"DEBUG: Signup Error: {e}")
        return False

def check_user(username, password):
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            
            # Returns the user's ID if found and password matches, otherwise None
            if result and check_password_hash(result[1], password):
                return result[0]
            return None
    except sqlite3.Error as e:
        print(f"DEBUG: Auth Error: {e}")
        return None

# 3. EXPENSE OPERATIONS (Filtered by USER_ID)
def insert_expense(USER_ID, category, amount, date=None):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            connection.execute('''
                INSERT INTO expenses (USER_ID, CATEGORY, AMOUNT, DATE) 
                VALUES (?, ?, ?, ?)
            ''', (USER_ID, category, amount, date))
            connection.commit()
            return True 
    except sqlite3.Error as e:
        print(f"DEBUG: Insertion Error: {e}")
        return False

def delete_expense(expense_id):
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            # We use ID (the specific expense row ID) for deletion
            connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            connection.commit()
            return True
    except sqlite3.Error as e:
        print(f"DEBUG: Deletion Error: {e}")
        return False

def view_expenses(USER_ID):
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            cursor = connection.cursor()
            # Fetch only the rows belonging to the logged-in user
            cursor.execute("SELECT * FROM expenses WHERE USER_ID = ?", (USER_ID,))
            return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"DEBUG: Fetch Error: {e}")
        return [] 

def total_expense(USER_ID):
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            cursor = connection.cursor()
            # COALESCE handles the case where a new user has 0 expenses (returns 0 instead of None)
            cursor.execute("SELECT COALESCE(SUM(AMOUNT), 0) FROM expenses WHERE USER_ID = ?", (USER_ID,))
            result = cursor.fetchone()[0]
            return float(result)
    except sqlite3.Error as e:
        print(f"DEBUG: Sum Error: {e}")
        return 0.0
    
def get_username(user_id):
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else "Guest"
    except sqlite3.Error as e:
        print(f"DEBUG: Get Username Error: {e}")
        return "User"
    
# Function to log and delete
def delete_expense_with_history(expense_id, user_id):
    try:
        with sqlite3.connect("finance_tracker.db") as connection:
            cursor = connection.cursor()
            
            # Step A: Fetch the data before we delete it
            cursor.execute("SELECT CATEGORY, AMOUNT, DATE FROM expenses WHERE id = ? AND USER_ID = ?", (expense_id, user_id))
            data = cursor.fetchone()
            
            if data:
                category, amount, exp_date = data
                deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Step B: Insert into history table
                cursor.execute('''INSERT INTO delete_history (USER_ID, CATEGORY, AMOUNT, EXPENSE_DATE, DELETED_AT) 
                                  VALUES (?, ?, ?, ?, ?)''', (user_id, category, amount, exp_date, deleted_at))
                
                # Step C: Actually delete the expense
                cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
                connection.commit()
                return True
            return False
    except sqlite3.Error as e:
        print(f"DEBUG: Delete History Error: {e}")
        return False

# Function to view history
def view_delete_history(user_id):
    with sqlite3.connect("finance_tracker.db") as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT CATEGORY, AMOUNT, EXPENSE_DATE, DELETED_AT FROM delete_history WHERE USER_ID = ? ORDER BY DELETED_AT DESC", (user_id,))
        return cursor.fetchall()