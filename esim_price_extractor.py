import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time
import threading
import sys
import os
import io

# --- Helper Class to Redirect stdout to the GUI Log ---
class TextRedirector(io.TextIOBase):
    """A helper class to redirect print statements to a Tkinter Text widget."""
    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        self.widget.configure(state='normal')
        self.widget.insert('end', text)
        self.widget.see('end')  # Auto-scroll to the bottom
        self.widget.configure(state='disabled')
        return len(text)

# --- Main Application Class ---
class ScraperApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="litera", title="eSIM Data Scraper")
        self.geometry("1000x600")
        self.minsize(800, 500)

        # Application state variables
        self.is_running = False
        self.is_paused = False
        self.scraper_thread = None

        # --- Main Layout ---
        # Configure the grid layout: sidebar (weight 1), log area (weight 3)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=250)
        self.grid_columnconfigure(1, weight=3)

        self._create_sidebar()
        self._create_log_area()

    # ---------- Cross-platform: default save location in Documents ----------
    def _default_base_path(self, base_name: str) -> str:
        """
        Return a cross-platform default base path inside the user's Documents folder.
        Falls back to the user's home directory if Documents can't be used/created.
        """
        try:
            user_home = os.path.expanduser("~")
            docs = os.path.join(user_home, "Documents")
            if not os.path.exists(docs):
                try:
                    os.makedirs(docs, exist_ok=True)
                    print("Created missing 'Documents' folder at:", docs)
                except Exception as e:
                    print(f"Could not create 'Documents' ({e}). Falling back to home directory.")
                    docs = user_home
            return os.path.join(docs, base_name)
        except Exception as e:
            print(f"Error determining default save path ({e}). Using current working directory.")
            return os.path.join(os.getcwd(), base_name)

    def _create_sidebar(self):
        """Creates the left-hand sidebar with all the controls."""
        sidebar_frame = ttk.Frame(self, padding=(15, 15))
        sidebar_frame.grid(row=0, column=0, sticky="nsew")
        sidebar_frame.grid_rowconfigure(3, weight=1)  # Pushes controls to the top

        # --- Controls ---
        # Start/Pause Button
        self.start_pause_button = ttk.Button(
            sidebar_frame,
            text="Start Scraping",
            command=self.toggle_scraper,
            bootstyle="success-outline"
        )
        self.start_pause_button.grid(row=0, column=0, sticky="ew", pady=(0, 20))

        # --- File Output Group ---
        file_group = ttk.LabelFrame(sidebar_frame, text="Output File", padding=10)
        file_group.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        file_group.grid_columnconfigure(0, weight=1)  # Configure a single column to expand

        self.filetype_var = tk.StringVar(value="csv")
        # Default base filename in Documents, no extension (e.g., /Users/you/Documents/esim_data)
        default_base = self._default_base_path("esim_data")
        self.filename_var = tk.StringVar(value=default_base)

        self.filename_entry = ttk.Entry(file_group, textvariable=self.filename_var)
        self.filename_entry.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.filetype_combo = ttk.Combobox(
            file_group,
            textvariable=self.filetype_var,
            values=["csv", "xlsx"],
            state="readonly"
        )
        self.filetype_combo.grid(row=1, column=0, sticky="ew")

        # --- Providers Group ---
        providers_group = ttk.LabelFrame(sidebar_frame, text="Providers", padding=10)
        providers_group.grid(row=2, column=0, sticky="ew")

        # Checkbox variables
        self.saily_var = tk.BooleanVar(value=True)
        self.airalo_var = tk.BooleanVar(value=False)
        self.nomad_var = tk.BooleanVar(value=False)
        self.alo_var = tk.BooleanVar(value=False)

        # Checkboxes
        saily_check = ttk.Checkbutton(providers_group, text="Saily", variable=self.saily_var)
        saily_check.pack(anchor="w", pady=2)

        # Disabled checkboxes with placeholder commands
        airalo_check = ttk.Checkbutton(providers_group, text="Airalo", variable=self.airalo_var, state="disabled", command=self._placeholder_airalo)
        airalo_check.pack(anchor="w", pady=2)

        nomad_check = ttk.Checkbutton(providers_group, text="NomadSIM", variable=self.nomad_var, state="disabled", command=self._placeholder_nomad)
        nomad_check.pack(anchor="w", pady=2)

        alo_check = ttk.Checkbutton(providers_group, text="AloSIM", variable=self.alo_var, state="disabled", command=self._placeholder_alo)
        alo_check.pack(anchor="w", pady=2)

    def _create_log_area(self):
        """Creates the right-hand log area."""
        log_frame = ttk.Frame(self, padding=(15, 15))
        log_frame.grid(row=0, column=1, sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_label = ttk.Label(log_frame, text="Execution Log", font=("-size 12 -weight bold"))
        log_label.grid(row=0, column=0, sticky="nw", pady=(0, 5))

        self.log_widget = tk.Text(log_frame, wrap="word", state="disabled", height=10, font=("Courier New", 10))
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_widget.yview)
        self.log_widget.config(yscrollcommand=scrollbar.set)

        self.log_widget.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        # Redirect stdout to the log widget
        sys.stdout = TextRedirector(self.log_widget)
        print("Welcome to the eSIM Data Scraper! Configure settings and press Start.\n")

    # --- Control Logic ---
    def toggle_scraper(self):
        """Handles the logic for the Start/Pause/Resume button."""
        if not self.is_running:
            # --- VALIDATION ---
            if not self.filename_var.get().strip():
                messagebox.showwarning("Validation Error", "Please enter a filename (or full path) before starting.")
                return
            if not self.saily_var.get():  # Check if at least one provider is selected
                messagebox.showwarning("Validation Error", "Please select at least one provider (Saily) to scrape.")
                return

            self._start_scraper()
        else:
            # --- PAUSE / RESUME ---
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.start_pause_button.config(text="Resume Scraping", bootstyle="info-outline")
                print("\n--- Scraping Paused ---\n")
            else:
                self.start_pause_button.config(text="Pause Scraping", bootstyle="warning-outline")
                print("\n--- Scraping Resumed ---\n")

    def _start_scraper(self):
        """Initializes and starts the scraper thread."""
        self.is_running = True
        self.is_paused = False
        self.start_pause_button.config(text="Pause Scraping", bootstyle="warning-outline")
        self._toggle_controls_state("disabled")

        # Run the scraper in a separate thread to not freeze the GUI
        self.scraper_thread = threading.Thread(target=self.run_saily_scraper, daemon=True)
        self.scraper_thread.start()

    def _scraper_finished(self):
        """Resets the UI after the scraper has finished or an error occurred."""
        self.is_running = False
        self.is_paused = False
        self.start_pause_button.config(text="Start Scraping", bootstyle="success-outline")
        self._toggle_controls_state("normal")
        # Ensure combo box remains readonly
        self.filetype_combo.config(state="readonly")

    def _toggle_controls_state(self, state):
        """Disables or enables sidebar controls to prevent changes during scraping."""
        self.filename_entry.config(state=state)
        self.filetype_combo.config(state=state)
        # Note: We don't re-enable the disabled checkboxes
        for widget in self.winfo_children()[0].winfo_children()[2].winfo_children():
            if isinstance(widget, ttk.Checkbutton) and widget.cget('text') == 'Saily':
                widget.config(state=state)

    # --- Placeholder Functions ---
    def _placeholder_airalo(self):
        print("Scraping for Airalo is not yet implemented.")

    def _placeholder_nomad(self):
        print("Scraping for NomadSIM is not yet implemented.")

    def _placeholder_alo(self):
        print("Scraping for AloSIM is not yet implemented.")

    # --- Core Scraper Logic (Adapted from your script) ---
    def run_saily_scraper(self):
        """The main scraping logic, executed in a separate thread."""
        try:
            # --- 1. SETUP ---
            base_filename = self.filename_var.get().strip()  # Can be a name or full path (no extension required)
            file_extension = self.filetype_var.get().lower()

            # If user already typed an extension, strip it so we don't double-append
            root, ext = os.path.splitext(base_filename)
            if ext.lower() in [".csv", ".xlsx"]:
                base_filename = root

            full_filename = f"{base_filename}.{file_extension}"
            full_filename = os.path.abspath(full_filename)

            # Ensure the output directory exists (Documents or user-specified)
            out_dir = os.path.dirname(full_filename)
            try:
                if out_dir and not os.path.exists(out_dir):
                    print(f"Output directory '{out_dir}' does not exist. Creating it...")
                    os.makedirs(out_dir, exist_ok=True)
                    print(f"Output directory '{out_dir}' created.")
                elif out_dir:
                    print(f"Output directory '{out_dir}' already exists.")
                else:
                    print("Output directory is current working directory.")
            except Exception as e:
                messagebox.showerror("File Path Error", f"Could not create directory for '{full_filename}':\n{e}")
                print(f"Error creating directory for '{full_filename}': {e}")
                return

            df_columns = [
                'country', '1gb_price', '1gb_validity', '3gb_price', '3gb_validity',
                '5gb_price', '5gb_validity', '10gb_price', '10gb_validity',
                '20gb_price', '20gb_validity', 'unlimitedgb_price', 'unlimitedgb_validity'
            ]
            df = pd.DataFrame(columns=df_columns)

            # --- File Handling: Append or Create ---
            if os.path.exists(full_filename):
                print(f"File '{full_filename}' found. Reading existing data to append new rows.")
                try:
                    if file_extension == 'csv':
                        existing_df = pd.read_csv(full_filename)
                    else:  # xlsx
                        existing_df = pd.read_excel(full_filename)
                    df = pd.concat([existing_df, df], ignore_index=True)
                    # Drop duplicates to avoid re-scraping countries already in the file
                    if 'country' in df.columns:
                        df.drop_duplicates(subset=['country'], keep='first', inplace=True)
                except Exception as e:
                    print(f"Warning: Could not read existing file ('{full_filename}'): {e}")
            else:
                print(f"File '{full_filename}' not found. A new file will be created in:\n{out_dir or os.getcwd()}")

            # --- 2. BROWSER INITIALIZATION ---
            print("Starting browser...")
            options = webdriver.ChromeOptions()
            options.add_argument("--disable-search-engine-choice-screen")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])  # Suppress warnings
            # options.add_argument("--headless")  # Uncomment for headless mode

            # This suppresses the "DevTools listening on..." message
            service = Service(log_output=os.devnull)

            driver = webdriver.Chrome(service=service, options=options)
            print("Browser started successfully.")

            # --- 3. GET COUNTRY LIST ---
            print("Fetching list of all countries from saily.com...")
            driver.get('https://saily.com/all-destinations/')
            time.sleep(5)
            country_elements = driver.find_element(By.ID, 'country-list-items').find_elements(By.TAG_NAME, 'a')
            all_countries_urls = [elem.get_attribute('href') for elem in country_elements]
            print(f'{len(all_countries_urls)} countries found!')

            # --- 4. SCRAPING LOOP ---
            for i, country_url in enumerate(all_countries_urls):
                # --- PAUSE LOGIC ---
                while self.is_paused:
                    time.sleep(0.5)

                country_name = country_url.split('/')[-2].replace('esim-', '').replace('-', ' ').capitalize()

                # Skip if country already in DataFrame
                if not df.empty and 'country' in df.columns and country_name in df['country'].values:
                    print(f"({i+1}/{len(all_countries_urls)}) Skipping '{country_name}' - already in file.")
                    continue

                print(f"\n({i+1}/{len(all_countries_urls)}) Scraping data for: {country_name}")
                driver.get(country_url)
                time.sleep(2)  # Wait for page load

                # Basic Cloudflare check (can be improved)
                while True:
                    if 'blocked' in driver.page_source.lower() or 'checking if the site connection is secure' in driver.page_source.lower():
                        print('Cloudflare detected. Restart required....     :/ ')
                        time.sleep(5)
                        current_url = driver.current_url
                        driver.quit()
                        driver = webdriver.Chrome(service=service, options=options)
                        driver.get(current_url)
                        time.sleep(3)
                    else:
                        print('Cloudflare bypassed!                          :) ')
                        break

                # --- 5. DATA EXTRACTION ---
                data = {'country': country_name}
                plan_cards = driver.find_elements(By.XPATH, "//li[contains(@data-testid, 'destination-hero-plan-card')]")

                for card in plan_cards:
                    try:
                        gb_str = card.find_element(By.XPATH, ".//p[contains(text(), 'GB')]").text
                        val_str = card.find_element(By.XPATH, ".//p[contains(text(), 'days')]").text
                        price_str = card.find_element(By.XPATH, ".//p[contains(text(), 'US$')]").text

                        gb = 'unlimited' if 'Unlimited' in gb_str else gb_str.split(' ')[0]
                        val = val_str.split(' ')[0]
                        price = price_str.split('US$')[1]

                        data[f"{gb}gb_price"] = price
                        data[f"{gb}gb_validity"] = val
                    except Exception:
                        # Silently ignore cards that don't match the format
                        pass

                print(f"Data collected: {str(data)}")
                new_row_df = pd.DataFrame([data])
                df = pd.concat([df, new_row_df], ignore_index=True)

                # --- 6. SAVE PROGRESS ---
                try:
                    if file_extension == 'csv':
                        df.to_csv(full_filename, index=False)
                    else:
                        # requires 'openpyxl' in requirements
                        df.to_excel(full_filename, index=False)
                    print(f'Progress saved to {full_filename}')
                except Exception as e:
                    print(f"Error saving to '{full_filename}': {e}")
                time.sleep(1)  # Small delay between countries

        except Exception as e:
            print(f"\n--- AN ERROR OCCURRED ---")
            print(f"Error Type: {type(e).__name__}")
            print(f"Error Details: {e}")
            messagebox.showerror("Scraper Error", f"An error occurred during scraping. Please check the log for details.\n\n{e}")

        finally:
            print("\n--- Scraping process has finished or been stopped. ---")
            if 'driver' in locals() and driver:
                driver.quit()
            # Safely schedule the GUI update on the main thread
            self.after(0, self._scraper_finished)


if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()
