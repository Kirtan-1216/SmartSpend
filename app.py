# flask is the package and Flask is the class in the package. 
# We are importing the class and several helpful functions.
from flask import Flask, request, redirect, url_for, session, render_template, flash, jsonify
from datetime import timedelta
from db_manager import create_table, insert_expense, view_expenses, delete_expense, total_expense, add_user, check_user, get_username, delete_expense_with_history, view_delete_history
from db_manager import update_budget_limit, get_budget_limit, get_category_monthly_spend
import csv
from io import StringIO

app = Flask(__name__) 
# secret_key is required to encrypt the session data so users can't tamper with it.
app.secret_key = "zavsecret_-_hrteckey"

# --- SESSION CONFIGURATION ---
# This sets the "shelf life" of the login cookie to 30 days.
app.permanent_session_lifetime = timedelta(days=30) 

# Initialize database tables
create_table()

@app.route('/')
def home():
    if 'USER_ID' not in session:
        return redirect(url_for('login'))

    user_id = session['USER_ID']
    # NEW: Fetch the actual username to display a personalized greeting
    name = get_username(user_id)
    records = view_expenses(user_id) 
    total = total_expense(user_id)
    budget = get_budget_limit(user_id)
    
    # Pass 'user_name' and 'budget' to the HTML
    return render_template("ssindex.html", expenses=records, total_val=total, user_name=name, budget=budget)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password:
            if add_user(username, password):
                # Fetch the new ID to log them in automatically
                user_id = check_user(username, password)
                
                # Make session permanent (lasts after browser close)
                session.permanent = True 
                session['USER_ID'] = user_id
                
                flash("Account created successfully!", "success")
                return redirect(url_for('home'))
            else:
                flash("Username already taken! Please choose another.", "error")
    return render_template("signup.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, skip the login page
    if 'USER_ID' in session:
        return redirect(url_for('home')) 

    if request.method == 'POST': 
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_id = check_user(username, password)
        if user_id:
            session.clear() # Clear any old session data
            session.permanent = True # Activate the 30-day "Remember Me"
            session['USER_ID'] = user_id 
            flash("Logged in successfully!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password", "error")
            
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear() # Destroys the login session completely
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
def add():
    if 'USER_ID' not in session:
        return redirect(url_for('login'))
        
    category = request.form.get("category")
    amount = request.form.get("amount")
    
    if category and amount:
        # Use session['USER_ID'] to ensure expense is saved to the correct user
        if insert_expense(session['USER_ID'], category, float(amount)):
            flash("Expense added successfully!", "success")
            
            # Budget check
            b_limit = get_budget_limit(session['USER_ID'])
            if b_limit > 0:
                total_spend = total_expense(session['USER_ID'])
                if total_spend > b_limit:
                    flash(f"🚨 BUDGET EXCEEDED: Your spending (₹{total_spend:.2f}) passed the ₹{b_limit:.2f} limit!", "error")
        else:
            flash("Error saving expense.", "error")
        return redirect(url_for('home'))
    flash("Error: Missing data", "error")
    return redirect(url_for('home'))

@app.route('/smart_add', methods=['POST'])
def smart_add():
    """
    System Design:
    - Acts as the controller for the Smart Input subsystem, routing the natural language payload 
      to the parser and executing the insertion command on the database.
      
    System Analysis:
    - Input: Form data containing a raw string ('smart_input').
    - Process: Uses `process_natural_language` to identify variables, then calls `insert_expense`.
    - Output: Redirect to the home page with a success/error flash message.
    """
    if 'USER_ID' not in session:
        return redirect(url_for('login'))
        
    smart_text = request.form.get("smart_input")
    if smart_text:
        parsed_data = process_natural_language(smart_text)
        amount = parsed_data.get('amount')
        category = parsed_data.get('category')
        
        if amount and amount > 0:
            if insert_expense(session['USER_ID'], category, amount):
                flash(f"Smart added: ₹{amount} for {category}", "success")
                
                # Budget check
                b_limit = get_budget_limit(session['USER_ID'])
                if b_limit > 0:
                    total_spend = total_expense(session['USER_ID'])
                    if total_spend > b_limit:
                        flash(f"🚨 BUDGET EXCEEDED: Your spending (₹{total_spend:.2f}) passed the ₹{b_limit:.2f} limit!", "error")
            else:
                flash("Error saving expense from smart input.", "error")
        else:
            flash("Could not detect a valid amount. Please modify your text.", "error")
            
    return redirect(url_for('home'))

@app.route('/history')
def history():
    if 'USER_ID' not in session:
        return redirect(url_for('login'))
    
    user_id = session['USER_ID']
    name = get_username(user_id)
    # Fetch the history from the new table
    from db_manager import view_delete_history
    deleted_items = view_delete_history(user_id)
    
    return render_template("history.html", history=deleted_items, user_name=name)

# UPDATE your existing delete route to use the new function
@app.route('/delete/<int:id>')
def delete(id):
    if 'USER_ID' not in session: 
        return redirect(url_for('login'))
    from db_manager import delete_expense_with_history
    if delete_expense_with_history(id, session['USER_ID']):
        flash("Expense deleted successfully!", "success")
    else:
        flash("Failed to delete expense.", "error")
    return redirect(url_for('home'))

@app.route('/api/data')
def api_data():
    """
    System Design:
    - This route serves as the API endpoint for dashboard components.
      It decouples data processing from HTML rendering, enabling asynchronous fetching.
      
    System Analysis:
    - Input: the user's session identifier.
    - Process: Calls DB methods `get_category_totals` and `get_last_7_days_spending`.
    - Output: A JSON payload structured for Chart.js parsing.
    """
    if 'USER_ID' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = session['USER_ID']
    from db_manager import get_category_totals, get_last_7_days_spending
    
    cat_data = get_category_totals(user_id)
    days_data = get_last_7_days_spending(user_id)
    
    return jsonify({
        "categories": {row[0]: row[1] for row in cat_data},
        "days": {row[0]: row[1] for row in days_data}
    })

@app.route('/settings', methods=['POST'])
def settings():
    """
    System Design:
    - User Configuration API. Updates the user's budget preferences.
    """
    if 'USER_ID' not in session:
        return redirect(url_for('login'))
        
    budget = request.form.get('budget_limit')
    if budget:
        if update_budget_limit(session['USER_ID'], float(budget)):
            flash("Budget limit updated!", "success")
        else:
            flash("Failed to update budget limit.", "error")
            
    return redirect(url_for('home'))

@app.route('/export')
def export_csv():
    """
    System Design & System Analysis:
    - Purpose: Data Portability feature. Streams current user's expense records as CSV.
    - Process: Uses `csv.writer` with `io.StringIO` to format data and returns it via `Response()`.
    """
    if 'USER_ID' not in session:
        return redirect(url_for('login'))
        
    records = view_expenses(session['USER_ID'])
    
    # Write to a string buffer
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Category', 'Amount', 'Date'])
    
    for row in records:
        cw.writerow([row[0], row[2], row[3], row[4]])
        
    from flask import Response
    output = si.getvalue()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=expenses.csv"}
    )

# Ignition switch
if __name__ == '__main__':
    # debug=True automatically reloads the server when you save changes.
    app.run(debug=True)