"""
Google-Maps claim-checker with a Tkinter front-end
(autonavigates to https://www.google.com/search?q=placeholder&udm=1)

Install deps:
    pip install selenium pandas
Make sure the ChromeDriver version matches your Chrome.
"""

import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

import pandas as pd


# ──────────────────────────  Selenium helpers  ────────────────────────── #
START_URL = "https://www.google.com/maps/search/placeholder"


def create_incognito_browser() -> webdriver.Chrome:
    """Launch Chrome in incognito mode and open the start URL."""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--incognito")
    service = Service()  # looks for chromedriver on PATH
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("…starting browser")
    driver.get(START_URL)                       # ← automatic navigation
    time.sleep(1)
    try:
        for i in driver.find_elements(By.TAG_NAME, 'button'):
            if 'Accept all' in i.get_attribute('aria-label'):
                i.click() 
                break
    except:
        pass
    time.sleep(3)
    return driver


def captcha_check(driver: webdriver.Chrome, page_source: str):
    """Pause until the user solves Google's ‘unusual traffic’ captcha."""
    phrase = "our systems have detected unusual traffic"
    while phrase in page_source.lower():
        print("⚠️  Captcha detected – solve it in the browser window.")
        time.sleep(10)
        page_source = driver.find_element(By.TAG_NAME, 'html').text.lower()
    return driver


def get_profile(driver: webdriver.Chrome, term):
    """Extract business profile details from the Maps side panel."""
    try:
        for w in driver.find_elements(By.TAG_NAME, "c-wiz")[2:]:
            if "Show more details" in w.text and len(w.text) <= 20:
                w.click()
    except Exception:
        pass

    data = {}

    c_wiz_text = driver.find_element(By.CLASS_NAME, "tAiQdd").text.split("\n")
    data['search_term'] = term
    data["name"] = c_wiz_text[0]
    try:
        data["rating_score"] = c_wiz_text[1]
        data["rating_total"] = c_wiz_text[2][1:-1]
    except: 
        pass
    flag = False
    print('start')
    elements = driver.find_elements(By.TAG_NAME, 'div')
    print('elements: ', len(elements))
    for i in reversed(elements[-int(len(elements)/4):]):
        val = str(i.get_attribute('aria-label'))
        if 'Information for' in val:
            print('found information element: ', val)
            break
    for s in i.find_elements(By.TAG_NAME, 'button'):
        att = str(s.get_attribute('data-item-id'))
        if 'address' in att:
            try:
                data["address"] = s.get_attribute('aria-label').split(': ')[1]
            except Exception:
                pass
        if 'phone:tel:' in att:
            try:
                data["phone_number"] = s.get_attribute('aria-label').split(': ')[1] if '+' in s.get_attribute('aria-label') else ''
            except Exception:
                pass
    for s in i.find_elements(By.TAG_NAME, 'a'):
        att = str(s.get_attribute('data-item-id'))
        if 'authority' in att:
            try:
                data["website"] = s.get_attribute('aria-label').split(': ')[1]
            except Exception:
                pass
        if 'merchant' in att:
            if s.get_attribute('aria-label') == 'Claim this business':
                flag =True
        # try:
        # except:
            # pass
            # try:
            #     data["claim"] = val
            # except Exception:
            #     pass
    print("↳", data)
    return driver, data, flag


def clear_search(driver: webdriver.Chrome):
    """Erase the query textarea in Google Maps."""
    for _ in range(100):
        driver.find_element(By.CLASS_NAME, "fontBodyMedium.searchboxinput").send_keys(Keys.BACKSPACE)
    return driver


def scrape(driver: webdriver.Chrome, searches: list[str], csv_path: str):
    """Run claim-checking for each search term and append to CSV."""
    df = pd.read_csv(csv_path) if os.path.exists(csv_path) else pd.DataFrame()

    for term in searches:
        print(f"\n🔍 Searching: {term}")
        driver = clear_search(driver)
        textarea = driver.find_element(By.CLASS_NAME, "fontBodyMedium.searchboxinput")
        textarea.send_keys(term)
        textarea.send_keys(Keys.ENTER)
        time.sleep(4)

        res = [i for i in driver.find_elements(By.TAG_NAME, 'div') if 'Results for' in str(i.get_attribute('aria-label'))]
        count = 0
        while "You've reached the end of the list." not in driver.find_element(By.TAG_NAME, 'html').text:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", res[0])
            count+=1
            time.sleep(2)
            if count > 20:
                break


        results = driver.find_elements(By.CLASS_NAME, "hfpxzc")
        # if not results:
        #     print("  No result cards found – did you switch to Maps view?")
        #     break

        for listing in results:
            print("\n", "_" * 60, "\n")
            try:
                listing.click()
            except Exception:
                # print("  (click failed)")
                continue

            time.sleep(3)
            page_source = driver.find_element(By.TAG_NAME, 'html').text.lower()

            driver = captcha_check(driver, page_source)
            page_source = driver.find_element(By.TAG_NAME, 'html').text.lower()
            driver, data, flag = get_profile(driver, term)


            if flag:
                df = pd.concat([df, pd.DataFrame([data])])
                df.to_csv(csv_path, index=False)

    print(f"\n✅ Finished. Results stored in {csv_path}")
    df.to_csv(csv_path, index=False)

# ─────────────────────────────  Tkinter GUI  ───────────────────────────── #
class ScraperGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Google-Maps Claim-Checker")
        self.geometry("580x420")
        self.resizable(False, False)

        self.driver: webdriver.Chrome | None = None
        self.search_terms = tk.Variable(value=[])

        self._build_widgets()

    # --------------- layout --------------- #
    def _build_widgets(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Saved searches:").grid(row=0, column=0, sticky="w")
        self.listbox = tk.Listbox(frm, listvariable=self.search_terms,
                                  height=8, width=43, selectmode="single")
        self.listbox.grid(row=1, column=0, columnspan=3, pady=(0, 10), sticky="nsew")

        self.entry_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.entry_var, width=40).grid(row=2, column=0, sticky="w")
        ttk.Button(frm, text="Add search", command=self.add_search)\
            .grid(row=2, column=1, padx=4, sticky="e")
        ttk.Button(frm, text="Remove selected", command=self.remove_selected)\
            .grid(row=2, column=2, sticky="e")

        ttk.Label(frm, text="CSV output file:").grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.file_var = tk.StringVar(value="results.csv")
        ttk.Entry(frm, textvariable=self.file_var, width=40)\
            .grid(row=4, column=0, sticky="w")
        ttk.Button(frm, text="Browse…", command=self.browse_file)\
            .grid(row=4, column=1, sticky="e")

        ttk.Button(frm, text="Start Browser", command=self.launch_browser)\
            .grid(row=5, column=0, pady=(20, 0), sticky="w")
        ttk.Button(frm, text="Start Scraping", command=self.start_scraping)\
            .grid(row=5, column=2, pady=(20, 0), sticky="e")

        hint = (
            f"❗ The browser opens on:\n   {START_URL}\n"
            "   After it finishes loading, switch to the Maps tab or go to "
            "maps.google.com before clicking ‘Start Scraping’."
        )
        ttk.Label(frm, text=hint, wraplength=540, foreground="#555", justify="left")\
            .grid(row=6, column=0, columnspan=3, pady=(18, 0), sticky="w")

        frm.columnconfigure(0, weight=1)

    # --------------- callbacks --------------- #
    def add_search(self):
        term = self.entry_var.get().strip()
        if term:
            self.listbox.insert("end", term)
            self.entry_var.set("")

    def remove_selected(self):
        sel = self.listbox.curselection()
        if sel:
            self.listbox.delete(sel[0])

    def browse_file(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=self.file_var.get(),
            title="Choose output CSV",
        )
        if path:
            self.file_var.set(path)

    def launch_browser(self):
        if self.driver:
            messagebox.showinfo("Browser already running",
                                "A browser is already open.")
            return
        try:
            self.driver = create_incognito_browser()
        except Exception as err:
            messagebox.showerror("Selenium error", str(err))

    def start_scraping(self):
        if not self.driver:
            messagebox.showwarning("No browser", "Click ‘Start Browser’ first.")
            return
        searches = list(self.listbox.get(0, "end"))
        if not searches:
            messagebox.showwarning("No searches", "Add at least one search term.")
            return
        csv_file = os.path.abspath(self.file_var.get())
        os.makedirs(os.path.dirname(csv_file), exist_ok=True)
        self.withdraw()           # hide GUI while running
        try:
            scrape(self.driver, searches, csv_file)
        finally:
            self.deiconify()      # show again on finish


# ─────────────────────────────── main ─────────────────────────────── #
if __name__ == "__main__":
    ScraperGUI().mainloop()


