import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import smtplib
import logging
import logging.handlers
import os
import json
import random
import time
from threading import Thread
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import keyring
import requests
from cryptography.fernet import Fernet
import csv
import re
from html.parser import HTMLParser
from email.mime.base import MIMEBase
from email import encoders

# Configure encrypted logging
log_file = "shurikenmail_log.enc"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(log_file, maxBytes=1048576, backupCount=5),
        logging.StreamHandler()  # Log to console
    ]
)

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.alpha = 0.0
        self.after_id = None
        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def schedule_show(self, event=None):
        self.after_id = self.widget.after(500, self.show_tooltip)

    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.widget.winfo_viewable():
            return
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, "bbox") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip_window, text=self.text, background="#f0f0f0", foreground="#333333",
                         relief="solid", borderwidth=1, font=("Segoe UI", 8), wraplength=150, padx=5, pady=3)
        label.pack()
        self.fade_in()

    def fade_in(self):
        self.alpha += 0.1
        if self.alpha < 1.0 and self.tooltip_window:
            try:
                self.tooltip_window.attributes("-alpha", self.alpha)
                self.after_id = self.widget.after(50, self.fade_in)
            except (tk.TclError, AttributeError):
                self.hide_tooltip()
        elif self.tooltip_window:
            try:
                self.tooltip_window.attributes("-alpha", 1.0)
            except (tk.TclError, AttributeError):
                self.hide_tooltip()

    def hide_tooltip(self, event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.tooltip_window:
            try:
                self.tooltip_window.destroy()
            except tk.TclError:
                pass
            self.tooltip_window = None
        self.alpha = 0.0

class HTMLPreviewParser(HTMLParser):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        if tag == "b":
            self.text_widget.tag_configure("bold", font=("Segoe UI", 9, "bold"))
            self.text_widget.insert(tk.END, "", "bold")
        elif tag == "i":
            self.text_widget.tag_configure("italic", font=("Segoe UI", 9, "italic"))
            self.text_widget.insert(tk.END, "", "italic")

    def handle_endtag(self, tag):
        self.current_tag = None

    def handle_data(self, data):
        self.text_widget.insert(tk.END, data, self.current_tag or "")

class ShurikenMail:
    def __init__(self, root):
        self.root = root
        self.root.title("ShurikenMail")
        self.root.geometry("800x600")
        self.root.resizable(False, False)
        self.config_file = "shurikenmail_config.json"
        self.config = {}
        self.load_config()
        self.is_dark_mode = self.config.get("theme", "light") == "dark"
        self.notification_queue = []

        try:
            self.setup_gui()
            self.cipher = self.init_cipher()
            self.save_config()
        except Exception as e:
            logging.error(f"Initialization failed: {e}")
            messagebox.showerror("Error", f"Failed to start ShurikenMail: {e}")
            raise

    def setup_gui(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        self.root.configure(bg="#f5f5f5" if not self.is_dark_mode else "#252526")
        self.root.bind("<Control-s>", lambda e: self.save_config())
        self.root.bind("<Control-p>", lambda e: self.update_preview())
        self.root.bind("<Control-Return>", lambda e: self.start_sending())

        self.toolbar = tk.Frame(self.root, bg="#0078d4", height=30)
        self.toolbar.pack(fill=tk.X)
        self.logo_label = tk.Label(self.toolbar, text="ShurikenMail", font=("Segoe UI Semibold", 12), fg="#ffffff", bg="#0078d4")
        self.logo_label.pack(side=tk.LEFT, padx=5)
        self.save_config_button = tk.Button(self.toolbar, text="💾", font=("Segoe UI", 10), bg="#0078d4", fg="#ffffff", bd=0, command=self.save_config)
        self.save_config_button.pack(side=tk.LEFT, padx=5)
        Tooltip(self.save_config_button, "Save configuration (Ctrl+S)")
        self.clear_form_button = tk.Button(self.toolbar, text="🗑️", font=("Segoe UI", 10), bg="#0078d4", fg="#ffffff", bd=0, command=self.clear_form)
        self.clear_form_button.pack(side=tk.LEFT, padx=5)
        Tooltip(self.clear_form_button, "Clear form")
        self.theme_button = tk.Button(self.toolbar, text="🌙" if not self.is_dark_mode else "☀️", font=("Segoe UI", 10), bg="#0078d4", fg="#ffffff", bd=0, command=self.toggle_theme)
        self.theme_button.pack(side=tk.RIGHT, padx=5)
        Tooltip(self.theme_button, "Toggle light/dark mode")
        for btn in [self.save_config_button, self.clear_form_button, self.theme_button]:
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#005a9e"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#0078d4"))

        self.sidebar = tk.Frame(self.root, bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", width=50)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.consent_var = tk.BooleanVar()
        self.consent_label = ttk.Label(self.sidebar, text="✔" if self.consent_var.get() else "☐", font=("Segoe UI", 10))
        self.consent_label.pack(pady=10)
        self.consent_label.bind("<Button-1>", self.toggle_consent)
        self.consent_label.bind("<Enter>", lambda e: self.consent_label.config(background="#e0e0e0" if not self.is_dark_mode else "#333333"))
        self.consent_label.bind("<Leave>", lambda e: self.consent_label.config(background="#f5f5f5" if not self.is_dark_mode else "#1e1e1e"))
        Tooltip(self.consent_label, "Confirm ethical use\nRequired to send emails")

        self.main_frame = tk.Frame(self.root, bg="#f5f5f5" if not self.is_dark_mode else "#252526")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.smtp_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.smtp_tab, text="SMTP Settings")
        self.smtp_frame = ttk.Frame(self.smtp_tab, padding="5")
        self.smtp_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.smtp_frame, text="SMTP Server:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.smtp_var = tk.StringVar(value=self.config.get("smtp_server", "smtp.gmail.com"))
        ttk.Combobox(self.smtp_frame, textvariable=self.smtp_var, values=["smtp.gmail.com", "smtp.mail.yahoo.com", "smtp-mail.outlook.com"], font=("Segoe UI", 9)).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(self.smtp_frame, text="SMTP Port:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=2)
        self.port_var = tk.StringVar(value=self.config.get("smtp_port", "587"))
        ttk.Entry(self.smtp_frame, textvariable=self.port_var, font=("Segoe UI", 9)).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(self.smtp_frame, text="Your Email:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=2)
        self.email_var = tk.StringVar(value=self.config.get("email", ""))
        ttk.Entry(self.smtp_frame, textvariable=self.email_var, font=("Segoe UI", 9)).grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Label(self.smtp_frame, text="Password/App Key:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=2)
        self.pass_var = tk.StringVar()
        ttk.Entry(self.smtp_frame, textvariable=self.pass_var, show="*", font=("Segoe UI", 9)).grid(row=3, column=1, sticky="ew", padx=5)
        self.save_keyring_button = tk.Button(self.smtp_frame, text="🔒", font=("Segoe UI", 9), bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff", bd=0, command=self.save_password)
        self.save_keyring_button.grid(row=3, column=2, padx=5)
        self.save_keyring_button.bind("<Enter>", lambda e: self.save_keyring_button.config(bg="#d0d0d0" if not self.is_dark_mode else "#444444"))
        self.save_keyring_button.bind("<Leave>", lambda e: self.save_keyring_button.config(bg="#e0e0e0" if not self.is_dark_mode else "#333333"))
        Tooltip(self.save_keyring_button, "Save password securely")

        self.content_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.content_tab, text="Email Content")
        self.content_frame = ttk.Frame(self.content_tab, padding="5")
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.content_frame, text="Recipient Emails:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        self.targets_text = tk.Text(self.content_frame, height=4, width=40, font=("Segoe UI", 9), bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.targets_text.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        self.targets_text.insert(tk.END, "Enter emails, one per line, or load a CSV")
        self.targets_text.bind("<FocusIn>", self.clear_placeholder)
        self.targets_text.bind("<FocusOut>", self.set_placeholder)
        self.load_csv_button = tk.Button(self.content_frame, text="📂", font=("Segoe UI", 9), bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff", bd=0, command=self.load_csv)
        self.load_csv_button.grid(row=1, column=2, padx=5)
        self.load_csv_button.bind("<Enter>", lambda e: self.load_csv_button.config(bg="#d0d0d0" if not self.is_dark_mode else "#444444"))
        self.load_csv_button.bind("<Leave>", lambda e: self.load_csv_button.config(bg="#e0e0e0" if not self.is_dark_mode else "#333333"))
        Tooltip(self.load_csv_button, "Load recipient list from CSV")
        ttk.Label(self.content_frame, text="Emails per Recipient:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=2)
        self.count_var = tk.StringVar(value="1")
        ttk.Combobox(self.content_frame, textvariable=self.count_var, values=["1", "25", "50", "100", "Custom"], font=("Segoe UI", 9)).grid(row=2, column=1, sticky="ew", padx=5)
        self.custom_count_var = tk.StringVar()
        self.custom_count_entry = ttk.Entry(self.content_frame, textvariable=self.custom_count_var, state="disabled", font=("Segoe UI", 9))
        self.custom_count_entry.grid(row=3, column=1, sticky="ew", padx=5)
        self.count_var.trace("w", self.toggle_custom_count)
        ttk.Label(self.content_frame, text="Subject:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", pady=2)
        self.subject_var = tk.StringVar(value="Test Email")
        ttk.Entry(self.content_frame, textvariable=self.subject_var, font=("Segoe UI", 9)).grid(row=4, column=1, sticky="ew", padx=5)
        ttk.Label(self.content_frame, text="Message:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", pady=2)
        self.message_text = tk.Text(self.content_frame, height=5, width=40, font=("Segoe UI", 9), bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.message_text.grid(row=5, column=1, sticky="ew", padx=5)
        self.message_text.insert(tk.END, "Hello,\nThis is a test email from ShurikenMail.\nBest,\n{sender}")
        ttk.Label(self.content_frame, text="Attachments:", font=("Segoe UI", 9)).grid(row=6, column=0, sticky="w", pady=2)
        self.attachments_var = tk.StringVar()
        ttk.Entry(self.content_frame, textvariable=self.attachments_var, state="readonly", font=("Segoe UI", 9)).grid(row=6, column=1, sticky="ew", padx=5)
        self.browse_attach_button = tk.Button(self.content_frame, text="📎", font=("Segoe UI", 9), bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff", bd=0, command=self.browse_attachments)
        self.browse_attach_button.grid(row=6, column=2, padx=5)
        self.browse_attach_button.bind("<Enter>", lambda e: self.browse_attach_button.config(bg="#d0d0d0" if not self.is_dark_mode else "#444444"))
        self.browse_attach_button.bind("<Leave>", lambda e: self.browse_attach_button.config(bg="#e0e0e0" if not self.is_dark_mode else "#333333"))
        Tooltip(self.browse_attach_button, "Add attachments (max 25MB; for videos >20MB, use Google Drive)")

        self.preview_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_tab, text="Preview")
        self.preview_frame = ttk.Frame(self.preview_tab, padding="5")
        self.preview_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.preview_frame, text="Email Preview:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=2)
        self.preview_text = tk.Text(self.preview_frame, height=8, width=50, font=("Segoe UI", 9), bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff", state="disabled")
        self.preview_text.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5)
        self.preview_buttons_frame = ttk.Frame(self.preview_frame)
        self.preview_buttons_frame.grid(row=0, column=1, sticky="e")
        self.update_preview_button = tk.Button(self.preview_buttons_frame, text="🔄", font=("Segoe UI", 9), bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff", bd=0, command=self.update_preview)
        self.update_preview_button.pack(side=tk.LEFT, padx=5)
        self.update_preview_button.bind("<Enter>", lambda e: self.update_preview_button.config(bg="#d0d0d0" if not self.is_dark_mode else "#444444"))
        self.update_preview_button.bind("<Leave>", lambda e: self.update_preview_button.config(bg="#e0e0e0" if not self.is_dark_mode else "#333333"))
        Tooltip(self.update_preview_button, "Refresh preview (Ctrl+P)")
        self.test_send_button = tk.Button(self.preview_buttons_frame, text="📧", font=("Segoe UI", 9), bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff", bd=0, command=self.test_send)
        self.test_send_button.pack(side=tk.LEFT, padx=5)
        self.test_send_button.bind("<Enter>", lambda e: self.test_send_button.config(bg="#d0d0d0" if not self.is_dark_mode else "#444444"))
        self.test_send_button.bind("<Leave>", lambda e: self.test_send_button.config(bg="#e0e0e0" if not self.is_dark_mode else "#333333"))
        Tooltip(self.test_send_button, "Send test email to your address")

        self.action_frame = tk.Frame(self.main_frame, bg="#f5f5f5" if not self.is_dark_mode else "#252526")
        self.action_frame.pack(fill=tk.X, pady=5)
        self.send_button = tk.Button(self.action_frame, text="📤 Send Emails", font=("Segoe UI", 12), bg="#dc3545", fg="#ffffff", bd=0, command=self.start_sending, width=12, padx=5, pady=3)
        self.send_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.send_button.bind("<Enter>", lambda e: self.send_button.config(bg="#218838"))
        self.send_button.bind("<Leave>", lambda e: self.send_button.config(bg="#28a745"))
        Tooltip(self.send_button, "Send emails to recipients (Ctrl+Enter)")

        self.status_frame = tk.Frame(self.main_frame, bg="#f5f5f5" if not self.is_dark_mode else "#252526")
        self.status_frame.pack(fill=tk.X, pady=5)
        self.status_label = ttk.Label(self.status_frame, text="Ready", font=("Segoe UI", 9))
        self.status_label.pack(side=tk.LEFT, padx=10)
        self.progress = ttk.Progressbar(self.status_frame, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.log_toggle_button = tk.Button(self.status_frame, text="📜", font=("Segoe UI", 9), bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff", bd=0, command=self.toggle_log_viewer)
        self.log_toggle_button.pack(side=tk.RIGHT, padx=10)
        self.log_toggle_button.bind("<Enter>", lambda e: self.log_toggle_button.config(bg="#d0d0d0" if not self.is_dark_mode else "#444444"))
        self.log_toggle_button.bind("<Leave>", lambda e: self.log_toggle_button.config(bg="#e0e0e0" if not self.is_dark_mode else "#333333"))
        Tooltip(self.log_toggle_button, "Show/hide log viewer")
        self.log_frame = tk.Frame(self.main_frame, bg="#f5f5f5" if not self.is_dark_mode else "#252526")
        self.log_text = tk.Text(self.log_frame, height=5, font=("Segoe UI", 9), bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff", state="disabled")
        self.log_text.pack(fill=tk.X, padx=10, pady=5)
        self.log_key_var = tk.StringVar(value=self.config.get("fernet_key", ""))
        ttk.Entry(self.log_frame, textvariable=self.log_key_var, font=("Segoe UI", 9), show="*").pack(fill=tk.X, padx=10, pady=5)
        Tooltip(self.log_frame, "Enter Fernet key to decrypt logs")
        self.log_visible = False

        self.notification_frame = tk.Frame(self.main_frame, bg="#f5f5f5" if not self.is_dark_mode else "#252526")
        self.notification_frame.pack(fill=tk.X, pady=5)
        self.notification_label = ttk.Label(self.notification_frame, text="", font=("Segoe UI", 9), background="#ffebee", foreground="#d32f2f")
        self.notification_label.pack(fill=tk.X, padx=10, pady=5)
        self.notification_label.bind("<Button-1>", self.handle_notification_click)

    def init_cipher(self):
        fernet_key = self.config.get("fernet_key")
        if not fernet_key:
            fernet_key = Fernet.generate_key().decode()
            self.config["fernet_key"] = fernet_key
        return Fernet(fernet_key.encode())

    def configure_styles(self):
        light_styles = {
            "TLabel": {"background": "#f5f5f5", "foreground": "#333333", "font": ("Segoe UI", 9), "padding": 2},
            "TEntry": {"fieldbackground": "#ffffff", "foreground": "#333333", "font": ("Segoe UI", 9), "borderwidth": 1, "relief": "flat"},
            "TCombobox": {"fieldbackground": "#ffffff", "foreground": "#333333", "font": ("Segoe UI", 9), "borderwidth": 1},
            "TNotebook": {"background": "#f5f5f5", "padding": 2},
            "TNotebook.Tab": {"background": "#e0e0e0", "foreground": "#333333", "font": ("Segoe UI Semibold", 9), "padding": [8, 3]},
            "TProgressbar": {"background": "#0078d4", "troughcolor": "#e0e0e0"}
        }
        dark_styles = {
            "TLabel": {"background": "#252526", "foreground": "#ffffff", "font": ("Segoe UI", 9), "padding": 2},
            "TEntry": {"fieldbackground": "#1e1e1e", "foreground": "#ffffff", "font": ("Segoe UI", 9), "borderwidth": 1, "relief": "flat"},
            "TCombobox": {"fieldbackground": "#1e1e1e", "foreground": "#ffffff", "font": ("Segoe UI", 9), "borderwidth": 1},
            "TNotebook": {"background": "#252526", "padding": 2},
            "TNotebook.Tab": {"background": "#333333", "foreground": "#ffffff", "font": ("Segoe UI Semibold", 9), "padding": [8, 3]},
            "TProgressbar": {"background": "#0078d4", "troughcolor": "#333333"}
        }
        styles = dark_styles if self.is_dark_mode else light_styles
        for widget, config in styles.items():
            self.style.configure(widget, **config)
        self.style.map("TNotebook.Tab", background=[("selected", "#ffffff" if not self.is_dark_mode else "#1e1e1e"), ("active", "#d0d0d0" if not self.is_dark_mode else "#444444")])

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.config["theme"] = "dark" if self.is_dark_mode else "light"
        self.save_config()
        self.configure_styles()
        bg = "#f5f5f5" if not self.is_dark_mode else "#252526"
        self.root.configure(bg=bg)
        self.main_frame.configure(bg=bg)
        self.action_frame.configure(bg=bg)
        self.status_frame.configure(bg=bg)
        self.notification_frame.configure(bg=bg)
        self.sidebar.configure(bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e")
        self.theme_button.config(text="☀️" if self.is_dark_mode else "🌙")
        for frame in [self.smtp_frame, self.content_frame, self.preview_frame]:
            for child in frame.winfo_children():
                if isinstance(child, (ttk.Label, ttk.Entry, ttk.Combobox)):
                    child.configure(style=child.winfo_class())
        for button in [self.save_keyring_button, self.load_csv_button, self.browse_attach_button, self.update_preview_button, self.test_send_button, self.log_toggle_button]:
            button.configure(bg="#e0e0e0" if not self.is_dark_mode else "#333333", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.send_button.configure(bg="#28a745", fg="#ffffff")
        self.targets_text.configure(bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.message_text.configure(bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.preview_text.configure(bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.log_text.configure(bg="#f5f5f5" if not self.is_dark_mode else "#1e1e1e", fg="#333333" if not self.is_dark_mode else "#ffffff")
        self.log_frame.configure(bg="#f5f5f5" if not self.is_dark_mode else "#252526")

    def toggle_log_viewer(self):
        if self.log_visible:
            self.log_frame.pack_forget()
            self.log_visible = False
        else:
            self.log_frame.pack(fill=tk.X, pady=5)
            self.log_visible = True
            self.update_log_viewer()

    def update_log_viewer(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        key = self.log_key_var.get()
        if not key:
            self.log_text.insert(tk.END, f"Enter Fernet key (check {self.config_file})")
            self.log_text.config(state="disabled")
            return
        try:
            fernet = Fernet(key.encode())
            with open(log_file, "rb") as f:
                for line in f:
                    try:
                        decrypted = fernet.decrypt(line.strip()).decode()
                        self.log_text.insert(tk.END, decrypted + "\n")
                    except:
                        self.log_text.insert(tk.END, "[Decryption Failed]\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"Error loading logs: {e}")
        self.log_text.config(state="disabled")

    def show_notification(self, message, action=None):
        self.notification_queue.append((message, action))
        if len(self.notification_queue) == 1:
            self.display_notification()

    def display_notification(self):
        if not self.notification_queue:
            self.notification_label.config(text="")
            self.notification_frame.pack_forget()
            return
        message, action = self.notification_queue[0]
        self.notification_frame.pack(fill=tk.X, pady=5)
        self.notification_label.config(text=message)
        self.notification_action = action
        self.root.after(5000, self.clear_notification)

    def clear_notification(self):
        self.notification_queue.pop(0)
        self.display_notification()

    def handle_notification_click(self, event):
        if self.notification_action:
            self.notification_action()
            self.clear_notification()

    def clear_form(self):
        self.smtp_var.set("smtp.gmail.com")
        self.port_var.set("587")
        self.email_var.set("")
        self.pass_var.set("")
        self.targets_text.delete("1.0", tk.END)
        self.set_placeholder(None)
        self.subject_var.set("Test Email")
        self.message_text.delete("1.0", tk.END)
        self.message_text.insert(tk.END, "Hello,\nThis is a test email from ShurikenMail.\nBest,\n{sender}")
        self.attachments_var.set("")
        self.count_var.set("1")
        self.custom_count_var.set("")
        self.consent_var.set(False)
        self.consent_label.config(text="☐")
        self.status_label.config(text="Form cleared")

    def toggle_consent(self, event):
        self.consent_var.set(not self.consent_var.get())
        self.consent_label.config(text="✔" if self.consent_var.get() else "☐")

    def clear_placeholder(self, event):
        if self.targets_text.get("1.0", tk.END).strip() == "Enter emails, one per line, or load a CSV":
            self.targets_text.delete("1.0", tk.END)

    def set_placeholder(self, event):
        if not self.targets_text.get("1.0", tk.END).strip():
            self.targets_text.insert(tk.END, "Enter emails, one per line, or load a CSV")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.config = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load config: {e}")
                self.config = {}

    def save_config(self):
        config = {
            "theme": "dark" if self.is_dark_mode else "light",
            "fernet_key": self.config.get("fernet_key", ""),
            "smtp_server": self.smtp_var.get() if hasattr(self, "smtp_var") else "",
            "smtp_port": self.port_var.get() if hasattr(self, "port_var") else "",
            "email": self.email_var.get() if hasattr(self, "email_var") else ""
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=4)
            self.show_notification("Configuration saved")
        except Exception as e:
            logging.error(f"Failed to save config: {e}")
            self.show_notification(f"Failed to save config: {e}")

    def save_password(self):
        if self.email_var.get() and self.pass_var.get():
            try:
                keyring.set_password("ShurikenMail", self.email_var.get(), self.pass_var.get())
                self.show_notification("Password saved securely")
                self.pass_var.set("")
            except Exception as e:
                logging.error(f"Failed to save password: {e}")
                self.show_notification(f"Failed to save password: {e}")
        else:
            self.show_notification("Email and password required")

    def get_password(self):
        try:
            password = keyring.get_password("ShurikenMail", self.email_var.get())
            return password if password else self.pass_var.get()
        except Exception as e:
            logging.error(f"Failed to retrieve password: {e}")
            return self.pass_var.get()

    def load_csv(self):
        file = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if file:
            self.status_label.config(text="Loading CSV...")
            try:
                with open(file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    self.recipients = list(reader)
                    emails = [row["email"] for row in self.recipients if "email" in row and self.is_valid_email(row["email"])]
                    if not emails:
                        self.show_notification("No valid emails found in CSV")
                        return
                    self.targets_text.delete("1.0", tk.END)
                    self.targets_text.insert(tk.END, "\n".join(emails))
                    self.show_notification(f"Loaded {len(emails)} valid recipients from CSV")
            except Exception as e:
                logging.error(f"Failed to load CSV: {e}")
                self.show_notification(f"Failed to load CSV: {e}")
        self.status_label.config(text="Ready")

    def is_valid_email(self, email):
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

    def toggle_custom_count(self, *args):
        if self.count_var.get() == "Custom":
            self.custom_count_entry.config(state="normal")
        else:
            self.custom_count_entry.config(state="disabled")
            self.custom_count_var.set("")

    def browse_attachments(self):
        files = filedialog.askopenfilenames(filetypes=[("All files", "*.*"), ("Video files", "*.mp4 *.mov *.avi")])
        for file in files:
            if os.path.getsize(file) > 20 * 1024 * 1024:  # Warn for >20MB
                messagebox.showwarning("Large File", f"File {file} is over 20MB. Consider compressing or using a Google Drive link.")
        self.attachments_var.set(", ".join(files))
        self.show_notification(f"Added {len(files)} attachments")

    def check_spam_triggers(self, text):
        spam_words = ["free", "win", "urgent", "buy now", "guarantee", "click here", "limited offer"]
        score = sum(1 for word in spam_words if word in text.lower())
        score += 2 if re.search(r"[A-Z]{5,}", text) else 0
        score += 2 if re.search(r"![!]{2,}", text) else 0
        return score > 3, score

    def validate_inputs(self):
        if not self.consent_var.get():
            return False, "You must confirm ethical use."
        if not self.smtp_var.get() or not self.port_var.get():
            return False, "SMTP server and port are required."
        if not self.email_var.get() or not self.get_password():
            return False, "Email and password are required."
        targets = [t.strip() for t in self.targets_text.get("1.0", tk.END).split("\n") if t.strip() and t.strip() != "Enter emails, one per line, or load a CSV"]
        if not targets:
            return False, "At least one target email is required."
        invalid_emails = [t for t in targets if not self.is_valid_email(t)]
        if invalid_emails:
            return False, f"Invalid email(s): {', '.join(invalid_emails)}"
        try:
            count = int(self.custom_count_var.get()) if self.count_var.get() == "Custom" else int(self.count_var.get())
            if count < 1 or count > 100:
                return False, "Email count must be between 1 and 100."
        except ValueError:
            return False, "Invalid email count."
        if not self.subject_var.get() or not self.message_text.get("1.0", tk.END).strip():
            return False, "Subject and message are required."
        attachments = [a.strip() for a in self.attachments_var.get().split(",") if a.strip()]
        for file in attachments:
            if not os.path.exists(file):
                return False, f"Attachment not found: {file}"
            if os.path.getsize(file) > 25 * 1024 * 1024:
                return False, f"File {file} exceeds 25MB limit. Use a Google Drive link instead."
        spam_detected, spam_score = self.check_spam_triggers(self.subject_var.get() + " " + self.message_text.get("1.0", tk.END))
        if spam_detected:
            return False, f"Content likely to be flagged as spam (score: {spam_score}). Revise subject/message."
        return True, ""

    def update_preview(self):
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)
        targets = [t.strip() for t in self.targets_text.get("1.0", tk.END).split("\n") if t.strip() and t.strip() != "Enter emails, one per line, or load a CSV"]
        target = targets[0] if targets else "recipient@example.com"
        name = target.split("@")[0]
        try:
            subject = self.subject_var.get().format(name=name, sender=self.email_var.get())
            message = self.message_text.get("1.0", tk.END).strip().format(name=name, sender=self.email_var.get())
        except KeyError as e:
            self.show_notification(f"Invalid placeholder in subject/message: {e}")
            return
        html_message = f"<html><body>{message.replace('\n', '<br>')}</body></html>"
        self.preview_text.insert(tk.END, f"Subject: {subject}\n\n")
        parser = HTMLPreviewParser(self.preview_text)
        parser.feed(html_message)
        self.preview_text.config(state="disabled")
        self.show_notification("Preview updated (Ctrl+P)")

    def create_smtp_connection(self):
        smtp_server = self.smtp_var.get()
        port = int(self.port_var.get())
        email = self.email_var.get()
        password = self.get_password()
        timeout = 60  # Increased for video attachments

        for attempt in range(3):
            try:
                if port == 465:
                    server = smtplib.SMTP_SSL(smtp_server, port, timeout=timeout)
                else:
                    server = smtplib.SMTP(smtp_server, port, timeout=timeout)
                    server.starttls()
                server.login(email, password)
                server.ehlo()  # Keep-alive
                logging.info(f"SMTP connection established to {smtp_server}:{port}")
                return server
            except Exception as e:
                logging.warning(f"SMTP connection attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2)
        raise Exception("Failed to connect to SMTP server after 3 attempts")

    def send_email(self, server, to_email, subject, message, attachments):
        msg = MIMEMultipart("alternative")
        msg["From"] = self.email_var.get()
        msg["To"] = to_email
        msg["Subject"] = subject

        html_message = f"<html><body>{message.replace('\n', '<br>')}</body></html>"
        msg.attach(MIMEText(message, "plain"))
        msg.attach(MIMEText(html_message, "html"))

        for file in attachments:
            with open(file, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file)}")
            msg.attach(part)

        server.send_message(msg)
        server.noop()  # Keep-alive
        logging.info(f"Sent email to {to_email}")

    def test_send(self):
        valid, error = self.validate_inputs()
        if not valid:
            self.show_notification(error)
            return
        self.status_label.config(text="Sending test email...")
        logging.info(f"Attempting test send to {self.email_var.get()}")
        server = None
        try:
            server = self.create_smtp_connection()
            target = self.email_var.get()
            name = target.split("@")[0]
            subject = self.subject_var.get().format(name=name, sender=self.email_var.get())
            message = self.message_text.get("1.0", tk.END).strip().format(name=name, sender=self.email_var.get())
            attachments = [a.strip() for a in self.attachments_var.get().split(",") if a.strip()]
            self.send_email(server, target, subject, message, attachments)
            self.show_notification("Test email sent to your address")
            logging.info(f"Test email sent to {self.email_var.get()}")
        except Exception as e:
            error_msg = {
                "SMTPAuthenticationError": "Authentication failed. Check email/password or use App Password.",
                "SMTPConnectError": "Failed to connect to SMTP server. Check server/port or try port 465.",
                "SMTPServerDisconnected": "Server disconnected. Try again later or check network.",
                "SMTPRecipientsRefused": f"Recipient {self.email_var.get()} refused.",
                "SMTPDataError": "Server rejected email content. Check subject/message or attachments."
            }.get(type(e).__name__, f"Test send failed: {str(e)}")
            self.show_notification(error_msg, action=self.test_send)
            logging.error(f"Test send failed: {error_msg}")
        finally:
            if server:
                try:
                    server.quit()
                    logging.info("SMTP connection closed")
                except:
                    pass
            self.status_label.config(text="Ready")

    def start_sending(self):
        valid, error = self.validate_inputs()
        if not valid:
            self.show_notification(error)
            return
        self.save_config()
        self.send_button.config(state="disabled")
        self.status_label.config(text="Sending emails...")
        self.progress["value"] = 0
        Thread(target=self.send_emails, daemon=True).start()

    def send_emails(self):
        server = None
        try:
            count = int(self.custom_count_var.get()) if self.count_var.get() == "Custom" else int(self.count_var.get())
            targets = [t.strip() for t in self.targets_text.get("1.0", tk.END).split("\n") if t.strip() and t.strip() != "Enter emails, one per line, or load a CSV"]
            attachments = [a.strip() for a in self.attachments_var.get().split(",") if a.strip()]
            message_template = self.message_text.get("1.0", tk.END).strip()
            subject_template = self.subject_var.get()

            total_emails = len(targets) * count
            self.progress["maximum"] = total_emails
            sent_emails = 0
            failed_emails = []

            server = self.create_smtp_connection()

            for target in targets:
                recipient_data = next((r for r in getattr(self, "recipients", []) if r.get("email") == target), {"name": target.split("@")[0]})
                for i in range(count):
                    retries = 0
                    max_retries = 3
                    while retries <= max_retries:
                        try:
                            subject = subject_template.format(**recipient_data, sender=self.email_var.get())
                            message = message_template.format(**recipient_data, sender=self.email_var.get())
                            logging.info(f"Attempting to send email {i+1}/{count} to {target}")
                            self.send_email(server, target, subject, message, attachments)
                            sent_emails += 1
                            self.progress["value"] = sent_emails
                            self.status_label.config(text=f"Sent {sent_emails}/{total_emails} emails")
                            self.root.update()
                            logging.info(f"Sent email {i+1}/{count} to {target}")
                            time.sleep(random.uniform(1, 3))
                            break
                        except Exception as e:
                            retries += 1
                            error_msg = {
                                "SMTPRecipientsRefused": f"Recipient {target} refused.",
                                "SMTPDataError": "Server rejected email content. Check subject/message or attachments.",
                                "SMTPServerDisconnected": "Server disconnected. Reconnecting..."
                            }.get(type(e).__name__, f"Error sending to {target}: {str(e)}")
                            logging.warning(f"Retry {retries}/{max_retries} for {target}: {error_msg}")
                            if retries > max_retries:
                                failed_emails.append((target, error_msg))
                                logging.error(f"Failed to send email {i+1}/{count} to {target}: {error_msg}")
                                break
                            time.sleep(2 ** retries)
                            if "disconnected" in error_msg.lower():
                                try:
                                    server.quit()
                                    server = self.create_smtp_connection()
                                    logging.info(f"Reconnected to SMTP server")
                                except Exception as e:
                                    logging.warning(f"Reconnection failed: {e}")
                                    failed_emails.append((target, f"Reconnection failed: {str(e)}"))
                                    break

            if failed_emails:
                failed_list = "; ".join([f"{email}: {reason}" for email, reason in failed_emails])
                self.show_notification(f"Some emails failed: {failed_list}", action=self.start_sending)
            else:
                self.show_notification("Emails sent successfully!")
            logging.info(f"Email sending completed: {sent_emails}/{total_emails} sent, {len(failed_emails)} failed")
        except Exception as e:
            error_msg = {
                "SMTPAuthenticationError": "Authentication failed. Check email/password or use App Password.",
                "SMTPConnectError": "Failed to connect to SMTP server. Check server/port or try port 465.",
                "SMTPServerDisconnected": "Server disconnected. Try again later or check network."
            }.get(type(e).__name__, f"Failed to send emails: {e}")
            self.show_notification(error_msg, action=self.start_sending)
            logging.error(f"Error: {error_msg}")
        finally:
            if server:
                try:
                    server.quit()
                    logging.info("SMTP connection closed")
                except:
                    pass
            self.send_button.config(state="normal")
            self.status_label.config(text="Ready")
            self.progress["value"] = 0

if __name__ == "__main__":
    root = tk.Tk()
    try:
        app = ShurikenMail(root)
        root.mainloop()
    except Exception as e:
        logging.error(f"Application failed: {e}")
        messagebox.showerror("Error", f"ShurikenMail failed to start: {e}")