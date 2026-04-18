import requests

def run_tests():
    s = requests.Session()
    BASE_URL = "http://127.0.0.1:5000"
    
    # 1. Sign up
    print("Testing Signup...")
    resp = s.post(f"{BASE_URL}/signup", data={"username": "agent_test", "password": "secure123"})
    if "Account created successfully" in resp.text:
        print("✅ Signup successful and flash message seen.")
    elif "Username already taken" in resp.text:
        print("⚠️ User already exists. Logging in instead.")
        resp = s.post(f"{BASE_URL}/login", data={"username": "agent_test", "password": "secure123"})
        if "Logged in successfully" in resp.text:
            print("✅ Login successful and flash message seen.")
    
    # 2. Add an expense
    print("Testing Add Expense...")
    resp2 = s.post(f"{BASE_URL}/add", data={"category": "Test Automation", "amount": "99.99"})
    if "Expense added successfully" in resp2.text:
        print("✅ Expense added successfully and flash message seen.")
    
    # 3. Verify on dashboard
    resp3 = s.get(f"{BASE_URL}/")
    if "Test Automation" in resp3.text and "99.99" in resp3.text:
        print("✅ Expense is visible on the dashboard.")
    
    # 4. History check
    resp4 = s.get(f"{BASE_URL}/history")
    if "Deletion History" in resp4.text:
        print("✅ History page loads successfully.")
        
    # 5. Logout
    resp5 = s.get(f"{BASE_URL}/logout")
    if "You have been logged out" in resp5.text:
        print("✅ Logout successful and flash message seen.")

if __name__ == "__main__":
    run_tests()
