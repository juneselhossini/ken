"""
Google-Maps claim-checker with a Tkinter front-end
(autonavigates to https://www.google.com/search?q=placeholder&udm=1)

Install deps:
    pip install selenium pandas
Make sure the ChromeDriver version matches your Chrome.
"""

import os
import sys # Added for stdout/stderr redirection
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback # Added for logging exception tracebacks

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service

import pandas as pd


# ──────────────────────────  Selenium helpers  ────────────────────────── #
START_URL = "https://www.google.com/maps/search/placeholder"


def create_incognito_browser() -> webdriver.Chrome:
    """Launch Chrome in incognito mode and open the start URL."""
    print("Attempting to create incognito browser...")
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--incognito")
    # Ensure ChromeDriver is in PATH or specify its path:
    # service = Service(executable_path="/path/to/chromedriver")
    service = Service()  # looks for chromedriver on PATH
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("Browser process started.")
    driver.get(START_URL)                  # ← automatic navigation
    print(f"Navigated to START_URL: {START_URL}")
    time.sleep(1)
    try:
        # Attempt to click "Accept all" cookies button
        buttons = driver.find_elements(By.TAG_NAME, 'button')
        accepted = False
        for i in buttons:
            if 'Accept all' in i.get_attribute('aria-label'):
                print("Found 'Accept all' button, clicking...")
                i.click()
                accepted = True
                break
        if not accepted:
            print("No 'Accept all' button found or clicked via aria-label.")
    except Exception as e:
        print(f"Error during cookie acceptance: {e}", file=sys.stderr)
        pass # Continue even if cookie button fails
    time.sleep(3)
    print("Browser setup complete.")
    return driver


def captcha_check(driver: webdriver.Chrome, page_source: str):
    """Pause until the user solves Google's ‘unusual traffic’ captcha."""
    phrase = "our systems have detected unusual traffic"
    if phrase in page_source.lower():
        print("⚠️ Captcha detected – solve it in the browser window.", file=sys.stderr)
        while phrase in driver.find_element(By.TAG_NAME, 'html').text.lower(): # Re-check current page source
            print("Captcha still present. Please solve it. Checking again in 10 seconds...")
            time.sleep(10)
        print("Captcha seems to be resolved.")
    return driver


def get_profile(driver: webdriver.Chrome, term):
    """Extract business profile details from the Maps side panel."""
    print(f"Extracting profile for search term: {term}")
    data = {}
    data['search_term'] = term

    try:
        # Try to click "Show more details" if present (this might not always exist or be necessary)
        # This part is heuristic and might need adjustment based on page structure
        for w in driver.find_elements(By.TAG_NAME, "c-wiz")[2:]: # Slicing from 2 might be too specific
            if hasattr(w, 'text') and "Show more details" in w.text and len(w.text) <= 20: # Check for text attribute
                print("Found and clicked 'Show more details'.")
                w.click()
                time.sleep(1) # Wait for content to load after click
                break
    except Exception as e:
        print(f"Note: Could not click 'Show more details' (may not be present): {e}", file=sys.stderr)
        pass

    try:
        c_wiz_text_element = driver.find_element(By.CLASS_NAME, "tAiQdd")
        c_wiz_text = c_wiz_text_element.text.split("\n")
        data["name"] = c_wiz_text[0]
        print(f"  Name: {data['name']}")
        try:
            data["rating_score"] = c_wiz_text[1]
            data["rating_total"] = c_wiz_text[2][1:-1]
            print(f"  Rating: {data['rating_score']}, Total: {data['rating_total']}")
        except IndexError:
            print("  No rating information found in c_wiz_text.")
            pass # No rating info
    except Exception as e:
        print(f"Error extracting basic info (name/rating): {e}", file=sys.stderr)


    flag = False # Claim this business flag
    print("Searching for detailed information elements (address, phone, website, claim)...")
    
    # Revised logic for finding details: Look for a container with business info.
    # This often has an aria-label like "Information for [Business Name]"
    info_elements_candidates = driver.find_elements(By.XPATH, "//div[contains(@aria-label, 'Information for')]")
    
    if not info_elements_candidates:
        # Fallback or broader search if specific "Information for" div isn't found
        # This might happen if the panel structure changes.
        # Using a more general approach by looking at all divs is too broad and slow.
        # Let's try to find buttons/links with known data-item-id attributes more directly
        # if the primary information div isn't located.
        print("Primary 'Information for' element not found. Trying direct search for items.")
        all_buttons = driver.find_elements(By.TAG_NAME, 'button')
        all_links = driver.find_elements(By.TAG_NAME, 'a')
        
        search_elements = all_buttons + all_links
    else:
        # If "Information for" div is found, search within it for better context
        # Usually the first one is the main panel for the selected business
        info_element = info_elements_candidates[0] 
        print(f"Found information element: {info_element.get_attribute('aria-label')}")
        search_elements = info_element.find_elements(By.XPATH, ".//button | .//a") # Search within this element

    for s in search_elements:
        att = str(s.get_attribute('data-item-id'))
        aria_label = s.get_attribute('aria-label')
        
        if 'address' in att and aria_label:
            try:
                data["address"] = aria_label.split(': ')[1]
                print(f"  Address: {data['address']}")
            except IndexError:
                print(f"  Address found but format unexpected: {aria_label}")
        
        if 'phone:tel:' in att and aria_label:
            try:
                # Ensure it's a phone number, not 'Add phone number'
                phone_text = aria_label.split(': ')[1] if ': ' in aria_label else aria_label
                if any(char.isdigit() for char in phone_text): # Simple check for digits
                        data["phone_number"] = phone_text
                        print(f"  Phone: {data['phone_number']}")
                else:
                        print(f"  Skipping non-phone text for phone: {phone_text}")
            except IndexError:
                print(f"  Phone found but format unexpected: {aria_label}")

        if 'authority' in att and aria_label: # Website
            try:
                data["website"] = aria_label.split(': ')[1]
                print(f"  Website: {data['website']}")
            except IndexError:
                print(f"  Website found but format unexpected: {aria_label}")
        
        if 'merchant' in att and aria_label and 'Claim this business' in aria_label:
            print("  'Claim this business' found.")
            flag = True
            data["claim_status"] = "Claim this business" # Store status

    if not data.get("name"):
        print("Could not extract essential data (e.g., name). Profile data might be incomplete.", file=sys.stderr)

    print(f"↳ Profile data extracted: {data}")
    return driver, data, flag


def clear_search(driver: webdriver.Chrome):
    """Erase the query textarea in Google Maps."""
    try:
        search_box = driver.find_element(By.CLASS_NAME, "fontBodyMedium.searchboxinput")
        # More robust clear:
        search_box.click() # Focus
        # Send CTRL+A (or Command+A on Mac) then DELETE
        if sys.platform == "darwin": # macOS
            search_box.send_keys(Keys.COMMAND + "a")
        else: # Windows/Linux
            search_box.send_keys(Keys.CONTROL + "a")
        search_box.send_keys(Keys.DELETE)
        print("Search box cleared.")
    except Exception as e:
        print(f"Error clearing search box: {e}", file=sys.stderr)
    return driver


def scrape(driver: webdriver.Chrome, searches: list[str], csv_path: str):
    """Run claim-checking for each search term and append to CSV."""
    df = pd.read_csv(csv_path) if os.path.exists(csv_path) else pd.DataFrame(columns=['search_term', 'name', 'rating_score', 'rating_total', 'address', 'phone_number', 'website'])
    print(f"Initial CSV loaded. Rows: {len(df)}")

    for term in searches:
        print(f"\n🔍 Searching: {term}")
        driver = clear_search(driver)
        time.sleep(0.5) # Short pause after clearing
        try:
            textarea = driver.find_element(By.CLASS_NAME, "fontBodyMedium.searchboxinput")
            textarea.send_keys(term)
            textarea.send_keys(Keys.ENTER)
            print(f"Search term '{term}' submitted.")
        except Exception as e:
            print(f"Error inputting search term '{term}': {e}", file=sys.stderr)
            continue # Skip to next term if search input fails
        
        time.sleep(4) # Wait for search results to load

        # Scroll to load all results
        try:
            results_panel_candidates = [
                el for el in driver.find_elements(By.TAG_NAME, 'div') 
                if el.get_attribute('aria-label') and 'Results for' in el.get_attribute('aria-label')
            ]
            if not results_panel_candidates:
                print("Could not find results panel for scrolling.", file=sys.stderr)
            else:
                results_panel = results_panel_candidates[0]
                print("Scrolling results panel to load all listings...")
                scroll_count = 0
                max_scrolls = 20 # Safety break for scrolling
                last_height = driver.execute_script("return arguments[0].scrollHeight", results_panel)
                while scroll_count < max_scrolls:
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", results_panel)
                    time.sleep(2) # Wait for new results to load
                    new_height = driver.execute_script("return arguments[0].scrollHeight", results_panel)
                    if new_height == last_height:
                        if "You've reached the end of the list." in driver.page_source:
                            print("Reached end of list message.")
                        else:
                            print("Scroll height did not change, assuming end of list.")
                        break
                    last_height = new_height
                    scroll_count += 1
                    print(f"  Scrolled down (Attempt {scroll_count}).")
                if scroll_count >= max_scrolls:
                    print("Reached max scroll attempts.", file=sys.stderr)

        except Exception as e:
            print(f"Error during scrolling of results: {e}", file=sys.stderr)


        results = driver.find_elements(By.CLASS_NAME, "hfpxzc") # Business listing links
        print(f"Found {len(results)} potential listings for '{term}'.")
        if not results:
            print("  No result cards (hfpxzc) found. Ensure you are on the Google Maps search results page.")
            # break # Original script had break here, changed to continue for multi-search
            continue


        for i, listing_link in enumerate(results):
            print(f"\n--- Processing listing {i+1} of {len(results)} for '{term}' ---")
            try:
                # Scroll element into view before clicking
                driver.execute_script("arguments[0].scrollIntoView(true);", listing_link)
                time.sleep(0.5)
                listing_link.click()
                print("  Clicked on listing.")
            except Exception as e:
                print(f"  Error clicking listing: {e}", file=sys.stderr)
                # Try to close potential pop-ups or consent dialogs if click fails
                try:
                    body = driver.find_element(By.TAG_NAME, 'body')
                    body.send_keys(Keys.ESCAPE) # Press Escape to close overlays
                    print("  Sent ESCAPE key to close potential overlays.")
                    time.sleep(0.5)
                    listing_link.click() # Retry click
                    print("  Retried click successfully.")
                except Exception as e2:
                    print(f"  Retry click also failed or ESCAPE did not help: {e2}", file=sys.stderr)
                    continue # Skip to next listing

            time.sleep(3) # Wait for profile panel to load
            page_source_html = driver.find_element(By.TAG_NAME, 'html').text # Get text of current page
            
            driver = captcha_check(driver, page_source_html) # Check for captcha after interaction
            # page_source_html = driver.find_element(By.TAG_NAME, 'html').text # Re-fetch after captcha handling
            
            try:
                driver, data, flag = get_profile(driver, term) # Pass current term for context
            except Exception as e_profile:
                print(f"  Error getting profile details: {e_profile}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                continue # Skip if profile extraction fails critically

            if flag: # If "Claim this business" was found
                print(f"  Business '{data.get('name', 'N/A')}' can be claimed. Adding to CSV.")
                # Ensure all expected columns are present before concat
                expected_cols = ['search_term', 'name', 'rating_score', 'rating_total', 'address', 'phone_number', 'website', 'claim_status']
                for col in expected_cols:
                    if col not in data:
                        data[col] = None # Or pd.NA or empty string
                
                new_row_df = pd.DataFrame([data])
                df = pd.concat([df, new_row_df], ignore_index=True)
                try:
                    df.to_csv(csv_path, index=False)
                    print(f"  Saved to {csv_path}")
                except Exception as e_csv:
                    print(f"  Error saving to CSV {csv_path}: {e_csv}", file=sys.stderr)
            else:
                print(f"  Business '{data.get('name', 'N/A')}' - 'Claim this business' not found or already claimed.")

    print(f"\n✅ Finished processing all search terms. Total results in CSV: {len(df)}")
    try:
        df.to_csv(csv_path, index=False) # Final save
        print(f"Final results securely stored in {csv_path}")
    except Exception as e_csv_final:
        print(f"Error during final save to CSV {csv_path}: {e_csv_final}", file=sys.stderr)


# ───────────────── TextRedirector for Tkinter Log Tab ────────────────── #
class TextRedirector:
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag

    def write(self, s):
        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, s, (self.tag,))
        self.widget.see(tk.END)  # Auto-scroll
        self.widget.update_idletasks() # Ensure GUI updates
        self.widget.config(state=tk.DISABLED)

    def flush(self):
        # Tkinter's Text widget doesn't need an explicit flush for this purpose
        pass

# ─────────────────────────────  Tkinter GUI  ───────────────────────────── #
class ScraperGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Google-Maps Claim-Checker")
        self.geometry("700x750") # Adjusted size for log tab
        self.resizable(True, True) # Allow resizing

        self.driver: webdriver.Chrome | None = None
        self.search_terms = tk.Variable(value=[])

        self._build_widgets()

        # Redirect stdout and stderr AFTER log_text widget is created
        # Store original streams if you ever need to restore them (e.g., in a __del__ or on_close method)
        # self.original_stdout = sys.stdout
        # self.original_stderr = sys.stderr
        sys.stdout = TextRedirector(self.log_text_widget, "stdout_tag")
        sys.stderr = TextRedirector(self.log_text_widget, "stderr_tag")

        # Configure tags for different colors in the log
        self.log_text_widget.tag_configure("stdout_tag", foreground="#007ACC") # Blueish
        self.log_text_widget.tag_configure("stderr_tag", foreground="red", font=('TkDefaultFont', 9, 'bold'))

        # Initial log message
        self.log_text_widget.config(state=tk.NORMAL)
        self.log_text_widget.insert(tk.END, "GUI Initialized. Application logs will appear here.\n", "stdout_tag")
        self.log_text_widget.config(state=tk.DISABLED)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)


    def _build_widgets(self):
        # Main notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, fill="both", expand=True)

        # --- Scraper Tab ---
        scraper_tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(scraper_tab, text='Scraper Controls')

        ttk.Label(scraper_tab, text="Saved searches:").grid(row=0, column=0, sticky="w", pady=(0,2))
        self.listbox = tk.Listbox(scraper_tab, listvariable=self.search_terms,
                                   height=10, width=50, selectmode="single", exportselection=False)
        self.listbox.grid(row=1, column=0, columnspan=3, pady=(0, 10), sticky="nsew")
        
        # Scrollbar for listbox
        listbox_scrollbar = ttk.Scrollbar(scraper_tab, orient="vertical", command=self.listbox.yview)
        listbox_scrollbar.grid(row=1, column=3, sticky="ns", pady=(0,10))
        self.listbox.configure(yscrollcommand=listbox_scrollbar.set)


        self.entry_var = tk.StringVar()
        search_entry = ttk.Entry(scraper_tab, textvariable=self.entry_var, width=45)
        search_entry.grid(row=2, column=0, sticky="ew", pady=(5,5))
        search_entry.bind("<Return>", lambda event: self.add_search())


        add_button = ttk.Button(scraper_tab, text="Add Search", command=self.add_search)
        add_button.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        remove_button = ttk.Button(scraper_tab, text="Remove Selected", command=self.remove_selected)
        remove_button.grid(row=2, column=2, padx=5, pady=5, sticky="ew")

        ttk.Label(scraper_tab, text="CSV output file:").grid(row=3, column=0, sticky="w", pady=(12, 2))
        
        # --- MODIFICATION FOR DEFAULT CSV PATH ---
        # Default to 'Maps_results.csv' in the user's Documents folder
        default_csv_filename = "Maps_results.csv" # You can change the default filename here
        try:
            # os.path.expanduser("~") gets the user's home directory
            # Works on both macOS (/Users/username) and Windows (C:\Users\username)
            user_documents_path = os.path.join(os.path.expanduser("~"), "Documents")
            
            # Check if Documents folder exists, if not, try to create it or fallback
            if not os.path.exists(user_documents_path):
                try:
                    print(f"User 'Documents' folder not found at {user_documents_path}, attempting to create it.")
                    os.makedirs(user_documents_path, exist_ok=True)
                    print(f"Successfully created 'Documents' folder.")
                except Exception as e_mkdir:
                    print(f"Could not create 'Documents' folder ({e_mkdir}). Falling back to user's home directory.", file=sys.stderr)
                    user_documents_path = os.path.expanduser("~") # Save to home directory instead
            
            default_save_path = os.path.join(user_documents_path, default_csv_filename)
            print(f"Default CSV save path set to: {default_save_path}")

        except Exception as e_path:
            # Absolute fallback if home directory somehow can't be determined or Documents path fails
            print(f"Error determining default save path ({e_path}). Falling back to local filename.", file=sys.stderr)
            default_save_path = default_csv_filename # Will save to current working dir (problematic for .app)
        
        self.file_var = tk.StringVar(value=default_save_path)
        # --- END OF MODIFICATION ---
        
        file_entry = ttk.Entry(scraper_tab, textvariable=self.file_var, width=45)
        file_entry.grid(row=4, column=0, sticky="ew", pady=(0,5))
        
        browse_button = ttk.Button(scraper_tab, text="Browse…", command=self.browse_file)
        browse_button.grid(row=4, column=1, columnspan=2, padx=5, pady=(0,5), sticky="ew")

        # Action Buttons Frame
        action_buttons_frame = ttk.Frame(scraper_tab)
        action_buttons_frame.grid(row=5, column=0, columnspan=3, pady=(20,0), sticky="ew")

        self.start_browser_button = ttk.Button(action_buttons_frame, text="Start Browser", command=self.launch_browser)
        self.start_browser_button.pack(side="left", expand=True, fill="x", padx=2)
        
        self.start_scraping_button = ttk.Button(action_buttons_frame, text="Start Scraping", command=self.start_scraping, state=tk.DISABLED)
        self.start_scraping_button.pack(side="left", expand=True, fill="x", padx=2)


        hint = (
            f"ℹ️ Browser opens on: {START_URL}\n"
            "After it finishes loading, you might need to manually switch to the Maps tab "
            "or navigate to a Google Maps page if it doesn't redirect automatically, "
            "before clicking ‘Start Scraping’."
        )
        hint_label = ttk.Label(scraper_tab, text=hint, wraplength=600, foreground="#333", justify="left", font=('TkDefaultFont', 9))
        hint_label.grid(row=6, column=0, columnspan=3, pady=(18, 0), sticky="w")

        scraper_tab.columnconfigure(0, weight=3) # Entry field gets more weight
        scraper_tab.columnconfigure(1, weight=1)
        scraper_tab.columnconfigure(2, weight=1)
        scraper_tab.rowconfigure(1, weight=1) # Listbox expands


        # --- Log Tab ---
        log_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(log_tab, text='Log')

        self.log_text_widget = tk.Text(log_tab, wrap=tk.WORD, state=tk.NORMAL, height=20, relief=tk.SUNKEN, borderwidth=1, font=('TkDefaultFont', 9))
        
        log_scrollbar_y = ttk.Scrollbar(log_tab, orient=tk.VERTICAL, command=self.log_text_widget.yview)
        self.log_text_widget.config(yscrollcommand=log_scrollbar_y.set)

        log_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Initial message and state=tk.DISABLED will be handled in __init__ after TextRedirector setup.

    # --------------- callbacks --------------- #
    def add_search(self):
        term = self.entry_var.get().strip()
        if term:
            current_items = list(self.listbox.get(0, "end"))
            if term not in current_items:
                self.listbox.insert("end", term)
                self.entry_var.set("")
                print(f"Added search term: {term}")
            else:
                print(f"Search term '{term}' already in the list.")
                messagebox.showinfo("Duplicate", f"The search term '{term}' is already in the list.")
        else:
            messagebox.showwarning("Empty Search", "Cannot add an empty search term.")


    def remove_selected(self):
        sel = self.listbox.curselection()
        if sel:
            term = self.listbox.get(sel[0])
            self.listbox.delete(sel[0])
            print(f"Removed search term: {term}")
        else:
            messagebox.showwarning("No Selection", "Please select a search term to remove.")


    def browse_file(self):
        # Suggest initial directory based on current file_var or default if it's just a filename
        initial_dir_candidate = os.path.dirname(self.file_var.get())
        if not os.path.isdir(initial_dir_candidate) or initial_dir_candidate == "/": # Avoid root as initial dir
            try:
                initial_dir_candidate = os.path.join(os.path.expanduser("~"), "Documents")
                if not os.path.isdir(initial_dir_candidate):
                    initial_dir_candidate = os.path.expanduser("~")
            except Exception:
                initial_dir_candidate = os.getcwd() # Fallback to current working directory

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=os.path.basename(self.file_var.get()), # Use just the filename part
            initialdir=initial_dir_candidate, # Suggest a writable directory
            title="Choose output CSV file",
        )
        if path:
            self.file_var.set(path)
            print(f"Output CSV file set to: {path}")

    def launch_browser(self):
        if self.driver:
            messagebox.showinfo("Browser Status", "A browser instance is already running or was previously started.")
            print("Launch Browser: Browser already running or initialized.", file=sys.stderr)
            return
        try:
            print("Attempting to launch browser via Selenium...")
            self.start_browser_button.config(state=tk.DISABLED)
            self.update_idletasks()
            self.driver = create_incognito_browser()
            print("Browser launched successfully by Selenium.")
            messagebox.showinfo("Browser Started", "Browser has been launched. Please ensure you are on the Google Maps page and have accepted any initial dialogs before starting to scrape.")
            self.start_scraping_button.config(state=tk.NORMAL) # Enable scraping button
        except Exception as err:
            messagebox.showerror("Selenium Launch Error", f"Failed to launch browser: {err}\n\nCheck ChromeDriver installation and version.")
            print("----- Selenium Browser Launch Error -----", file=sys.stderr)
            traceback.print_exc(file=sys.stderr) # Prints full traceback to log tab
            self.driver = None # Ensure driver is None if launch failed
        finally:
            if self.driver is None: # If launch failed
                self.start_browser_button.config(state=tk.NORMAL) # Re-enable button
            else: # If successful
                self.start_browser_button.config(text="Browser Running", state=tk.DISABLED)


    def start_scraping(self):
        if not self.driver:
            messagebox.showwarning("Browser Not Ready", "Please click ‘Start Browser’ first and ensure it's ready.")
            print("Start Scraping: Browser not available.", file=sys.stderr)
            return
        
        searches = list(self.listbox.get(0, "end"))
        if not searches:
            messagebox.showwarning("No Search Terms", "Please add at least one search term to the list.")
            print("Start Scraping: No search terms provided.", file=sys.stderr)
            return
            
        csv_file_path_str = self.file_var.get().strip()
        if not csv_file_path_str:
            messagebox.showwarning("No CSV File", "Please specify an output CSV file path.")
            print("Start Scraping: CSV file path is empty.", file=sys.stderr)
            return

        # Ensure the directory for the CSV file exists
        csv_abs_path = os.path.abspath(csv_file_path_str)
        csv_dir = os.path.dirname(csv_abs_path)
        try:
            if csv_dir and not os.path.exists(csv_dir): # Only create if dirname is not empty and doesn't exist
                print(f"Output directory '{csv_dir}' does not exist. Attempting to create.")
                os.makedirs(csv_dir, exist_ok=True)
                print(f"Output directory '{csv_dir}' ensured.")
            elif os.path.exists(csv_dir):
                 print(f"Output directory '{csv_dir}' already exists.")
            else: # csv_dir is empty, meaning current directory
                 print(f"Output directory is current working directory.")

        except Exception as e:
            messagebox.showerror("File Path Error", f"Could not create directory for '{csv_abs_path}': {e}")
            print(f"Error creating directory for CSV '{csv_abs_path}': {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return

        # self.withdraw()  # Hide GUI while running - consider making this optional or providing progress
        print(f"Starting scraping process for {len(searches)} terms. Output will be saved to {csv_abs_path}")
        self.start_scraping_button.config(state=tk.DISABLED, text="Scraping...")
        self.update_idletasks()
        try:
            scrape(self.driver, searches, csv_abs_path)
            print("Scraping process completed successfully.")
            messagebox.showinfo("Scraping Finished", f"Scraping complete. Results saved to {csv_abs_path}")
        except Exception as e:
            messagebox.showerror("Scraping Error", f"An unexpected error occurred during scraping: {e}")
            print("----- An error occurred during the scraping process -----", file=sys.stderr)
            traceback.print_exc(file=sys.stderr) # Log the full traceback
        finally:
            # self.deiconify()  # Show again on finish
            self.start_scraping_button.config(state=tk.NORMAL, text="Start Scraping")
            print("Scraping GUI controls re-enabled.")
            
    def on_closing(self):
        print("Close button clicked. Shutting down...")
        if self.driver:
            try:
                print("Attempting to quit the browser...")
                self.driver.quit()
                print("Browser quit successfully.")
            except Exception as e:
                print(f"Error quitting browser: {e}", file=sys.stderr)
        # Restore stdout/stderr if they were stored
        # if hasattr(self, 'original_stdout'): sys.stdout = self.original_stdout
        # if hasattr(self, 'original_stderr'): sys.stderr = self.original_stderr
        self.destroy()


# ─────────────────────────────── main ─────────────────────────────── #
if __name__ == "__main__":
    app = ScraperGUI()
    app.mainloop()
