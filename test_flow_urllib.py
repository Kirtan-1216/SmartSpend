import urllib.request
import urllib.parse
import http.cookiejar

def run_tests():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    urllib.request.install_opener(opener)
    
    BASE_URL = "http://127.0.0.1:5000"
    
    print("Testing Signup...")
    data = urllib.parse.urlencode({"username": "agent_test2", "password": "secure123"}).encode("utf-8")
    resp = urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}/signup", data=data))
    text = resp.read().decode("utf-8")
    
    if "Account created successfully" in text:
        print("✅ Signup successful and flash message seen.")
    elif "already taken" in text:
        print("⚠️ User already exists. Logging in instead.")
        resp = urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}/login", data=data))
        text = resp.read().decode("utf-8")
        if "Logged in successfully" in text:
            print("✅ Login successful and flash message seen.")
    
    print("Testing Add Expense...")
    expense_data = urllib.parse.urlencode({"category": "Test Automation", "amount": "99.99"}).encode("utf-8")
    resp2 = urllib.request.urlopen(urllib.request.Request(f"{BASE_URL}/add", data=expense_data))
    text2 = resp2.read().decode("utf-8")
    
    if "Expense added successfully" in text2:
        print("✅ Expense added successfully and flash message seen.")
        
    print("Testing Dashboard...")
    resp3 = urllib.request.urlopen(f"{BASE_URL}/")
    text3 = resp3.read().decode("utf-8")
    if "Test Automation" in text3 and "99.99" in text3:
        print("✅ Expense is visible on the dashboard.")
    
    print("Testing Logout...")
    resp4 = urllib.request.urlopen(f"{BASE_URL}/logout")
    text4 = resp4.read().decode("utf-8")
    if "You have been logged out" in text4:
        print("✅ Logout successful and flash message seen.")

if __name__ == "__main__":
    run_tests()
