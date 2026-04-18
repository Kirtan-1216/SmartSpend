# flask is the package and Flask is the class in the package. 
# We are importing the class and several helpful functions.
from flask import Flask, request, redirect, url_for, session, render_template, flash
from datetime import timedelta
from db_manager import create_table, insert_expense, view_expenses, delete_expense, total_expense, add_user, check_user, get_username, delete_expense_with_history, view_delete_history

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
    
    # Pass 'user_name' to the HTML
    return render_template("ssindex.html", expenses=records, total_val=total, user_name=name)

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
        else:
            flash("Error saving expense.", "error")
        return redirect(url_for('home'))
    flash("Error: Missing data", "error")
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

# Ignition switch
if __name__ == '__main__':
    # debug=True automatically reloads the server when you save changes.
    app.run(debug=True)