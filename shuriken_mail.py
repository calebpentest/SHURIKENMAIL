import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import smtplib
import logging
import logging.handlers
import os
import json
import time
from threading import Thread
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import keyring
from cryptography.fernet import Fernet
import csv
import re
from html.parser import HTMLParser
from email.mime.base import MIMEBase
from email import encoders

# Configure encrypted logging
log_file = "shurikenmail_log.enc"
audit_log_file = "shurikenmail_audit.log"
class SanitizeFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', str(record.msg))
        return True

class EncryptedFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, filename, cipher, mode='ab', maxBytes=0, backupCount=0, encoding=None, delay=False):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.cipher = cipher
        if not os.path.exists(filename):
            with open(filename, 'wb') as f:
                f.write(self.cipher.encrypt(b"ShurikenMail Log Start\n"))

    def emit(self, record):
        try:
            msg = self.format(record)
            encrypted_msg = self.cipher.encrypt(msg.encode())
            with open(self.baseFilename, 'ab') as f:
                f.write(encrypted_msg + b'\n')
                f.flush()
            self.shouldRollover(record)
        except Exception as e:
            print(f"Logging error: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[]
)
logger = logging.getLogger()
logger.addFilter(SanitizeFilter())

# Audit logging
audit_logger = logging.getLogger('audit')
audit_handler = logging.handlers.RotatingFileHandler(audit_log_file, maxBytes=1048576, backupCount=5)
audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)

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
        label = tk.Label(self.tooltip_window, text=self.text, background="#FFFFFF", foreground="#000000",
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
        self.notification_queue = []

        # Initialize cipher and logging
        try:
            self.cipher = self.init_cipher()
            logger.addHandler(EncryptedFileHandler(log_file, self.cipher, maxBytes=1048576, backupCount=5))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize encryption: {e}")
            raise

        # PIN authentication
        if not self.authenticate_user():
            self.root.destroy()
            return

        # Ethical use disclaimer
        messagebox.showwarning(
            "Use it at your own risk",
            "ShurikenMail is for authorized phishing tests only. Use without permission is illegal and unethical."
        )

        try:
            self.setup_gui()
            self.save_config()
        except Exception as e:
            logging.error(f"Initialization failed: {e}")
            messagebox.showerror("Error", f"Failed to start ShurikenMail: {e}")
            raise

    def authenticate_user(self):
        pin = keyring.get_password("ShurikenMail", "app_pin")
        if not pin:
            pin = "1234"  # Default PIN
            keyring.set_password("ShurikenMail", "app_pin", pin)
        dialog = tk.Toplevel(self.root)
        dialog.title("Authentication")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        ttk.Label(dialog, text="Enter PIN:", font=("Segoe UI", 9)).pack(pady=10)
        pin_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=pin_var, show="*", font=("Segoe UI", 9)).pack(pady=5)
        result = [False]
        def verify():
            if pin_var.get() == pin:
                result[0] = True
                dialog.destroy()
            else:
                messagebox.showerror("Error", "Invalid PIN")
        ttk.Button(dialog, text="Submit", command=verify).pack(pady=10)
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result[0]

    def setup_gui(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        self.root.configure(bg="#FFFFFF")
        self.root.bind("<Control-s>", lambda e: self.save_config())
        self.root.bind("<Control-p>", lambda e: self.update_preview())
        self.root.bind("<Control-Return>", lambda e: self.start_sending())

        self.toolbar = tk.Frame(self.root, bg="#0078D4", height=30)
        self.toolbar.pack(fill=tk.X)
        self.logo_label = tk.Label(self.toolbar, text="ShurikenMail", font=("Segoe UI Semibold", 12), fg="#FFFFFF", bg="#0078D4")
        self.logo_label.pack(side=tk.LEFT, padx=10)
        self.save_config_button = tk.Button(self.toolbar, text="Save", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.save_config)
        self.save_config_button.pack(side=tk.LEFT, padx=10)
        Tooltip(self.save_config_button, "Save configuration (Ctrl+S)")
        self.clear_form_button = tk.Button(self.toolbar, text="Clear", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.clear_form)
        self.clear_form_button.pack(side=tk.LEFT, padx=10)
        Tooltip(self.clear_form_button, "Clear form")
        for btn in [self.save_config_button, self.clear_form_button]:
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#005A9E"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#0078D4"))

        self.sidebar = tk.Frame(self.root, bg="#FFFFFF", width=50)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.consent_var = tk.BooleanVar()
        self.consent_frame = tk.Frame(self.sidebar, bg="#FFFFFF")
        self.consent_frame.pack(pady=10)
        self.consent_label = ttk.Label(self.consent_frame, text="✔" if self.consent_var.get() else "☐", font=("Segoe UI", 10))
        self.consent_label.pack(side=tk.LEFT)
        ttk.Label(self.consent_frame, text="Authorized Use", font=("Segoe UI", 9), foreground="#D32F2F").pack(side=tk.LEFT, padx=5)
        self.consent_label.bind("<Button-1>", self.toggle_consent)
        self.consent_label.bind("<Enter>", lambda e: self.consent_label.config(background="#F0F0F0"))
        self.consent_label.bind("<Leave>", lambda e: self.consent_label.config(background="#FFFFFF"))
        Tooltip(self.consent_label, "Confirm authorized use only\nRequired to send emails")

        self.main_frame = tk.Frame(self.root, bg="#FFFFFF")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.smtp_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.smtp_tab, text="SMTP Settings")
        self.smtp_frame = ttk.Frame(self.smtp_tab, padding="10")
        self.smtp_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.smtp_frame, text="SMTP Server:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)
        self.smtp_var = tk.StringVar(value=self.config.get("smtp_server", "smtp.gmail.com"))
        ttk.Combobox(self.smtp_frame, textvariable=self.smtp_var, values=["smtp.gmail.com", "smtp.mail.yahoo.com", "smtp-mail.outlook.com"], font=("Segoe UI", 9), width=30).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(self.smtp_frame, text="SMTP Port:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=5)
        self.port_var = tk.StringVar(value=self.config.get("smtp_port", "587"))
        ttk.Entry(self.smtp_frame, textvariable=self.port_var, font=("Segoe UI", 9), width=30).grid(row=1, column=1, sticky="ew", padx=10)
        ttk.Label(self.smtp_frame, text="Your Email:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=5)
        self.email_var = tk.StringVar(value=self.config.get("email", ""))
        ttk.Entry(self.smtp_frame, textvariable=self.email_var, font=("Segoe UI", 9), width=30).grid(row=2, column=1, sticky="ew", padx=10)
        ttk.Label(self.smtp_frame, text="Password/App Key:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(self.smtp_frame, textvariable=self.pass_var, show="*", font=("Segoe UI", 9), width=30).grid(row=3, column=1, sticky="ew", padx=10)
        self.save_keyring_button = tk.Button(self.smtp_frame, text="Save Password", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.save_password)
        self.save_keyring_button.grid(row=3, column=2, padx=10)
        self.save_keyring_button.bind("<Enter>", lambda e: self.save_keyring_button.config(bg="#005A9E"))
        self.save_keyring_button.bind("<Leave>", lambda e: self.save_keyring_button.config(bg="#0078D4"))
        Tooltip(self.save_keyring_button, "Save password securely")

        self.content_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.content_tab, text="Email Content")
        self.content_frame = ttk.Frame(self.content_tab, padding="10")
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.content_frame, text="Recipient Emails:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.targets_text = tk.Text(self.content_frame, height=4, width=50, font=("Segoe UI", 9), bg="#FFFFFF", fg="#000000")
        self.targets_text.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)
        self.targets_text.insert(tk.END, "Enter emails, one per line, or load a CSV")
        self.targets_text.bind("<FocusIn>", self.clear_placeholder)
        self.targets_text.bind("<FocusOut>", self.set_placeholder)
        self.load_csv_button = tk.Button(self.content_frame, text="Load CSV", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.load_csv)
        self.load_csv_button.grid(row=1, column=2, padx=10)
        self.load_csv_button.bind("<Enter>", lambda e: self.load_csv_button.config(bg="#005A9E"))
        self.load_csv_button.bind("<Leave>", lambda e: self.load_csv_button.config(bg="#0078D4"))
        Tooltip(self.load_csv_button, "Load recipient list from CSV")
        ttk.Label(self.content_frame, text="Emails per Recipient:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=5)
        self.count_var = tk.StringVar(value="1")
        ttk.Combobox(self.content_frame, textvariable=self.count_var, values=["1", "25", "50", "100", "Custom"], font=("Segoe UI", 9), width=30).grid(row=2, column=1, sticky="ew", padx=10)
        self.custom_count_var = tk.StringVar()
        self.custom_count_entry = ttk.Entry(self.content_frame, textvariable=self.custom_count_var, state="disabled", font=("Segoe UI", 9), width=30)
        self.custom_count_entry.grid(row=3, column=1, sticky="ew", padx=10)
        self.count_var.trace("w", self.toggle_custom_count)
        ttk.Label(self.content_frame, text="Subject:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky="w", pady=5)
        self.subject_var = tk.StringVar(value="Test Email")
        self.subject_entry = ttk.Entry(self.content_frame, textvariable=self.subject_var, font=("Segoe UI", 9), width=30)
        self.subject_entry.grid(row=4, column=1, sticky="ew", padx=10)
        Tooltip(self.subject_entry, "Subject must be a single line (no newlines, max 78 characters)")
        self.subject_char_count = ttk.Label(self.content_frame, text="0/78", font=("Segoe UI", 8))
        self.subject_char_count.grid(row=4, column=2, sticky="w", padx=5)
        self.subject_var.trace("w", self.update_subject_char_count)
        ttk.Label(self.content_frame, text="Message:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", pady=5)
        self.message_text = tk.Text(self.content_frame, height=5, width=50, font=("Segoe UI", 9), bg="#FFFFFF", fg="#000000")
        self.message_text.grid(row=5, column=1, sticky="ew", padx=10)
        self.message_text.insert(tk.END, "Hello,\nThis is a test email from ShurikenMail.\nBest,\n{sender}")
        ttk.Label(self.content_frame, text="Attachments:", font=("Segoe UI", 9)).grid(row=6, column=0, sticky="w", pady=5)
        self.attachments_var = tk.StringVar()
        ttk.Entry(self.content_frame, textvariable=self.attachments_var, state="readonly", font=("Segoe UI", 9), width=30).grid(row=6, column=1, sticky="ew", padx=10)
        self.browse_attach_button = tk.Button(self.content_frame, text="Add Attachments", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.browse_attachments)
        self.browse_attach_button.grid(row=6, column=2, padx=10)
        self.browse_attach_button.bind("<Enter>", lambda e: self.browse_attach_button.config(bg="#005A9E"))
        self.browse_attach_button.bind("<Leave>", lambda e: self.browse_attach_button.config(bg="#0078D4"))
        Tooltip(self.browse_attach_button, "Add attachments (max 25MB; for files >20MB, use Google Drive)")

        self.preview_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.preview_tab, text="Preview")
        self.preview_frame = ttk.Frame(self.preview_tab, padding="10")
        self.preview_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.preview_frame, text="Email Preview:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)
        self.preview_text = tk.Text(self.preview_frame, height=8, width=50, font=("Segoe UI", 9), bg="#FFFFFF", fg="#000000", state="disabled")
        self.preview_text.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)
        self.preview_buttons_frame = ttk.Frame(self.preview_frame)
        self.preview_buttons_frame.grid(row=0, column=1, sticky="e")
        self.update_preview_button = tk.Button(self.preview_buttons_frame, text="Refresh", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.update_preview)
        self.update_preview_button.pack(side=tk.LEFT, padx=10)
        self.update_preview_button.bind("<Enter>", lambda e: self.update_preview_button.config(bg="#005A9E"))
        self.update_preview_button.bind("<Leave>", lambda e: self.update_preview_button.config(bg="#0078D4"))
        Tooltip(self.update_preview_button, "Refresh preview (Ctrl+P)")
        self.test_send_button = tk.Button(self.preview_buttons_frame, text="Test Send", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.test_send)
        self.test_send_button.pack(side=tk.LEFT, padx=10)
        self.test_send_button.bind("<Enter>", lambda e: self.test_send_button.config(bg="#005A9E"))
        self.test_send_button.bind("<Leave>", lambda e: self.test_send_button.config(bg="#0078D4"))
        Tooltip(self.test_send_button, "Send test email to your address")

        self.action_frame = tk.Frame(self.main_frame, bg="#FFFFFF")
        self.action_frame.pack(fill=tk.X, pady=10)
        self.send_button = tk.Button(self.action_frame, text="Send Emails", font=("Segoe UI", 12), bg="#28A745", fg="#FFFFFF", bd=0, command=self.start_sending, width=12)
        self.send_button.pack(side=tk.LEFT, padx=10)
        self.send_button.bind("<Enter>", lambda e: self.send_button.config(bg="#218838"))
        self.send_button.bind("<Leave>", lambda e: self.send_button.config(bg="#28A745"))
        Tooltip(self.send_button, "Send emails to recipients (Ctrl+Enter)")

        self.status_frame = tk.Frame(self.main_frame, bg="#FFFFFF")
        self.status_frame.pack(fill=tk.X, pady=10)
        self.status_label = ttk.Label(self.status_frame, text="Ready", font=("Segoe UI", 9))
        self.status_label.pack(side=tk.LEFT, padx=10)
        self.progress = ttk.Progressbar(self.status_frame, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.log_toggle_button = tk.Button(self.status_frame, text="View Logs", font=("Segoe UI", 9), bg="#0078D4", fg="#FFFFFF", bd=0, command=self.toggle_log_viewer)
        self.log_toggle_button.pack(side=tk.RIGHT, padx=10)
        self.log_toggle_button.bind("<Enter>", lambda e: self.log_toggle_button.config(bg="#005A9E"))
        self.log_toggle_button.bind("<Leave>", lambda e: self.log_toggle_button.config(bg="#0078D4"))
        Tooltip(self.log_toggle_button, "Show/hide log viewer")
        self.log_frame = tk.Frame(self.main_frame, bg="#FFFFFF")
        self.log_text = tk.Text(self.log_frame, height=5, font=("Segoe UI", 9), bg="#FFFFFF", fg="#000000", state="disabled")
        self.log_text.pack(fill=tk.X, padx=10, pady=5)
        self.reset_log_button = tk.Button(self.log_frame, text="Reset Logs", font=("Segoe UI", 9), bg="#D32F2F", fg="#FFFFFF", bd=0, command=self.reset_fernet_key)
        self.reset_log_button.pack(pady=5)
        self.reset_log_button.bind("<Enter>", lambda e: self.reset_log_button.config(bg="#B71C1C"))
        self.reset_log_button.bind("<Leave>", lambda e: self.reset_log_button.config(bg="#D32F2F"))
        Tooltip(self.reset_log_button, "Reset encryption key and clear logs")
        self.log_visible = False

        self.notification_frame = tk.Frame(self.main_frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        self.notification_frame.pack(fill=tk.X, pady=10)
        self.notification_label = ttk.Label(self.notification_frame, text="", font=("Segoe UI", 9), background="#FFEBEE", foreground="#D32F2F")
        self.notification_label.pack(fill=tk.X, padx=10, pady=5)
        self.notification_label.bind("<Button-1>", self.handle_notification_click)

    def configure_styles(self):
        styles = {
            "TLabel": {"background": "#FFFFFF", "foreground": "#000000", "font": ("Segoe UI", 9), "padding": 5},
            "TEntry": {"fieldbackground": "#FFFFFF", "foreground": "#000000", "font": ("Segoe UI", 9), "borderwidth": 1, "relief": "flat"},
            "TCombobox": {"fieldbackground": "#FFFFFF", "foreground": "#000000", "font": ("Segoe UI", 9), "borderwidth": 1},
            "TNotebook": {"background": "#FFFFFF", "padding": 5},
            "TNotebook.Tab": {"background": "#FFFFFF", "foreground": "#000000", "font": ("Segoe UI Semibold", 9), "padding": [10, 5]},
            "TProgressbar": {"background": "#0078D4", "troughcolor": "#FFFFFF"}
        }
        for widget, config in styles.items():
            self.style.configure(widget, **config)
        self.style.map("TNotebook.Tab", background=[("selected", "#0078D4"), ("active", "#F0F0F0")], foreground=[("selected", "#FFFFFF")])

    def update_subject_char_count(self, *args):
        length = len(self.subject_var.get())
        self.subject_char_count.config(text=f"{length}/78")
        if length > 78:
            self.subject_char_count.config(foreground="#D32F2F")
        else:
            self.subject_char_count.config(foreground="#000000")

    def init_cipher(self):
        fernet_key = keyring.get_password("ShurikenMail", "fernet_key")
        if not fernet_key:
            fernet_key = Fernet.generate_key().decode()
            keyring.set_password("ShurikenMail", "fernet_key", fernet_key)
        try:
            return Fernet(fernet_key.encode())
        except Exception as e:
            logging.error(f"Invalid Fernet key: {e}")
            raise ValueError("Invalid Fernet key in keyring")

    def reset_fernet_key(self):
        if messagebox.askokcancel("Confirm", "Resetting logs will clear all encrypted logs and generate a new encryption key. Continue?"):
            try:
                keyring.delete_password("ShurikenMail", "fernet_key")
                for file in [log_file] + [f"{log_file}.{i}" for i in range(1, 6)]:
                    if os.path.exists(file):
                        os.remove(file)
                self.cipher = self.init_cipher()
                logger.handlers = [h for h in logger.handlers if not isinstance(h, EncryptedFileHandler)]
                logger.addHandler(EncryptedFileHandler(log_file, self.cipher, maxBytes=1048576, backupCount=5))
                self.show_notification("Logs and encryption key reset successfully")
                audit_logger.info("Logs and Fernet key reset")
                self.update_log_viewer()
            except Exception as e:
                self.show_notification(f"Failed to reset logs: {e}")
                logging.error(f"Failed to reset logs: {e}")
                audit_logger.info(f"Failed to reset logs: {e}")

    def toggle_log_viewer(self):
        if self.log_visible:
            self.log_frame.pack_forget()
            self.log_visible = False
        else:
            self.log_frame.pack(fill=tk.X, pady=10)
            self.log_visible = True
            self.update_log_viewer()

    def update_log_viewer(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        key = keyring.get_password("ShurikenMail", "fernet_key")
        if not key:
            self.log_text.insert(tk.END, "Fernet key not found in keyring. Click 'Reset Logs' to generate a new key.")
            self.show_notification("Fernet key missing. Click 'Reset Logs' to fix.", action=self.reset_fernet_key)
            self.log_text.config(state="disabled")
            return
        try:
            fernet = Fernet(key.encode())
            if not os.path.exists(log_file) or os.path.getsize(log_file) == 0:
                self.log_text.insert(tk.END, "No logs available. Send emails to generate logs.")
                self.log_text.config(state="disabled")
                return
            with open(log_file, "rb") as f:
                for line in f:
                    try:
                        decrypted = fernet.decrypt(line.strip()).decode()
                        self.log_text.insert(tk.END, decrypted + "\n")
                    except Exception:
                        self.log_text.insert(tk.END, "Malformed log detected, not processing this one\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"Error loading logs: {e}\nClick 'Reset Logs' to clear and regenerate.")
            self.show_notification(f"Log decryption failed: {e}. Click 'Reset Logs' to fix.", action=self.reset_fernet_key)
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
        self.notification_frame.pack(fill=tk.X, pady=10)
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
            "smtp_server": self.smtp_var.get() if hasattr(self, "smtp_var") else "",
            "smtp_port": self.port_var.get() if hasattr(self, "port_var") else "",
            "email": self.email_var.get() if hasattr(self, "email_var") else ""
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=4)
            os.chmod(self.config_file, 0o600)
            self.show_notification("Configuration saved")
            audit_logger.info("Configuration saved")
        except Exception as e:
            logging.error(f"Failed to save config: {e}")
            self.show_notification(f"Failed to save config: {e}")

    def save_password(self):
        if self.email_var.get() and self.pass_var.get():
            try:
                keyring.set_password("ShurikenMail", self.email_var.get(), self.pass_var.get())
                self.show_notification("Password saved securely")
                audit_logger.info("Password saved to keyring")
            except Exception as e:
                logging.error(f"Failed to save password: {e}")
                self.show_notification(f"Failed to save password: {e}")
            finally:
                self.pass_var.set("")  # Clear password
        else:
            self.show_notification("Email and password required")

    def get_password(self):
        try:
            password = keyring.get_password("ShurikenMail", self.email_var.get())
            return password if password else self.pass_var.get()
        except Exception as e:
            logging.error(f"Failed to retrieve password: {e}")
            return self.pass_var.get()

    def is_valid_email(self, email):
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, email):
            return False
        try:
            domain = email.split('@')[1]
            import socket
            socket.gethostbyname(domain)
            return True
        except:
            return False

    def load_csv(self):
        file = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if file:
            self.status_label.config(text="Loading CSV...")
            try:
                with open(file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    self.recipients = []
                    for row in reader:
                        sanitized_row = {k: v.strip() for k, v in row.items()}
                        if "email" in sanitized_row:
                            if sanitized_row["email"].startswith(('=', '+', '-', '@')):
                                sanitized_row["email"] = f"'{sanitized_row['email']}"
                            if self.is_valid_email(sanitized_row["email"]):
                                self.recipients.append(sanitized_row)
                    emails = [row["email"] for row in self.recipients]
                    if not emails:
                        self.show_notification("No valid emails found in CSV")
                        return
                    self.targets_text.delete("1.0", tk.END)
                    self.targets_text.insert(tk.END, "\n".join(emails))
                    self.show_notification(f"Loaded {len(emails)} valid recipients from CSV")
                    audit_logger.info(f"Loaded CSV with {len(emails)} recipients")
            except Exception as e:
                logging.error(f"Failed to load CSV: {e}")
                self.show_notification(f"Failed to load CSV: {e}")
        self.status_label.config(text="Ready")

    def toggle_custom_count(self, *args):
        if self.count_var.get() == "Custom":
            self.custom_count_entry.config(state="normal")
        else:
            self.custom_count_entry.config(state="disabled")
            self.custom_count_var.set("")

    def browse_attachments(self):
        allowed_types = {
            '.pdf': b'%PDF-',
            '.png': b'\x89PNG\r\n\x1a\n',
            '.jpg': b'\xff\xd8\xff',
            '.mp4': b'\x00\x00\x00\x20ftypmp42'
        }
        files = filedialog.askopenfilenames(filetypes=[("Safe files", "*.pdf *.png *.jpg *.mp4")])
        valid_files = []
        for file in files:
            if os.path.getsize(file) > 25 * 1024 * 1024:
                messagebox.showwarning("Large File", f"File {file} exceeds 25MB.")
                continue
            if os.path.getsize(file) > 20 * 1024 * 1024:
                messagebox.showwarning("Large File", f"File {file} is over 20MB. Consider using a Google Drive link.")
            ext = os.path.splitext(file)[1].lower()
            if ext in allowed_types:
                with open(file, 'rb') as f:
                    header = f.read(8)
                    if header.startswith(allowed_types[ext]):
                        valid_files.append(file)
                    else:
                        messagebox.showwarning("Invalid File", f"File {file} has invalid content.")
            else:
                messagebox.showwarning("Unsupported File", f"File type {ext} not allowed.")
        self.attachments_var.set(", ".join(valid_files))
        self.show_notification(f"Added {len(valid_files)} attachments")
        audit_logger.info(f"Added {len(valid_files)} attachments")

    def check_spam_triggers(self, text):
        spam_words = ["free", "win", "urgent", "buy now", "guarantee", "click here", "limited offer"]
        score = sum(1 for word in spam_words if word in text.lower())
        score += 2 if re.search(r"[A-Z]{5,}", text) else 0
        score += 2 if re.search(r"![!]{2,}", text) else 0
        return score > 3, score

    def validate_inputs(self):
        if not self.consent_var.get():
            return False, "You must confirm authorized use."
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
            if len(targets) * count > 100:
                return False, "Total emails exceed recommended daily limit (100). Split into smaller batches."
        except ValueError:
            return False, "Invalid email count."
        subject = self.subject_var.get()
        message = self.message_text.get("1.0", tk.END).strip()
        if not subject or not message:
            return False, "Subject and message are required."
        if re.search(r'[\r\n]', subject):
            return False, "Subject cannot contain newline characters."
        if len(subject) > 78:
            return False, "Subject exceeds 78 characters."
        attachments = [a.strip() for a in self.attachments_var.get().split(",") if a.strip()]
        for file in attachments:
            if not os.path.exists(file):
                return False, f"Attachment not found: {file}"
            if os.path.getsize(file) > 25 * 1024 * 1024:
                return False, f"File {file} exceeds 25MB limit. Use a Google Drive link instead."
        spam_detected, spam_score = self.check_spam_triggers(subject + " " + message)
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
        audit_logger.info("Preview updated")

    def create_smtp_connection(self):
        smtp_server = self.smtp_var.get()
        port = int(self.port_var.get())
        email = self.email_var.get()
        password = self.get_password()
        timeout = 120

        for attempt in range(3):
            try:
                if port == 465:
                    server = smtplib.SMTP_SSL(smtp_server, port, timeout=timeout)
                else:
                    server = smtplib.SMTP(smtp_server, port, timeout=timeout)
                    server.starttls()
                server.login(email, password)
                server.ehlo()
                logging.info(f"SMTP connection established to {smtp_server}:{port}")
                audit_logger.info(f"SMTP connection established to {smtp_server}:{port}")
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
        msg.attach(MIMEText(message, "plain", "utf-8"))
        msg.attach(MIMEText(html_message, "html", "utf-8"))

        for file in attachments:
            with open(file, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file)}")
            msg.attach(part)

        server.send_message(msg)
        server.noop()
        logging.info("Sent email to recipient")

    def test_send(self):
        valid, error = self.validate_inputs()
        if not valid:
            self.show_notification(error)
            return
        self.status_label.config(text="Sending test email...")
        logging.info("Attempting test send to sender")
        audit_logger.info("Initiated test send")
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
            logging.info("Test email sent to sender")
            audit_logger.info("Test email sent successfully")
        except Exception as e:
            error_msg = {
                "SMTPAuthenticationError": "Authentication failed. Check email/password or use App Password.",
                "SMTPConnectError": "Failed to connect to SMTP server. Check server/port or try port 465.",
                "SMTPServerDisconnected": "Server disconnected. Try again later or check network.",
                "SMTPRecipientsRefused": "Recipient refused.",
                "SMTPDataError": "Server rejected email content. Check subject/message or attachments."
            }.get(type(e).__name__, f"Test send failed: {str(e)}")
            self.show_notification(error_msg, action=self.test_send)
            logging.error(f"Test send failed: {error_msg}")
            audit_logger.info(f"Test send failed: {error_msg}")
        finally:
            if server:
                try:
                    server.quit()
                    logging.info("SMTP connection closed")
                    audit_logger.info("SMTP connection closed")
                except:
                    pass
            self.status_label.config(text="Ready")

    def start_sending(self):
        valid, error = self.validate_inputs()
        if not valid:
            self.show_notification(error)
            return
        if not messagebox.askokcancel("Confirm", "Are you sure you want to send emails?"):
            return
        self.save_config()
        self.send_button.config(state="disabled")
        self.status_label.config(text="Sending emails...")
        self.progress["value"] = 0
        Thread(target=self.send_emails, daemon=True).start()
        audit_logger.info("Started email sending process")

    def send_emails(self):
        server = None
        try:
            count = int(self.custom_count_var.get()) if self.count_var.get() == "Custom" else int(self.count_var.get())
            targets = [t.strip() for t in self.targets_text.get("1.0", tk.END).split("\n") if t.strip() and t.strip() != "Enter emails, one per line, or load a CSV"]
            attachments = [a.strip() for a in self.attachments_var.get().split(",") if a.strip()]
            message_template = self.message_text.get("1.0", tk.END).strip()
            subject_template = self.subject_var.get()

            rate_limit = 10  # Emails per minute
            rate_interval = 60 / rate_limit
            total_emails = len(targets) * count
            self.progress["maximum"] = total_emails
            sent_emails = 0
            failed_emails = []

            server = self.create_smtp_connection()
            last_send_time = time.time()

            for target in targets:
                recipient_data = next((r for r in getattr(self, "recipients", []) if r.get("email") == target), {"name": target.split("@")[0]})
                for i in range(count):
                    current_time = time.time()
                    if current_time - last_send_time < rate_interval:
                        time.sleep(rate_interval - (current_time - last_send_time))
                    retries = 0
                    max_retries = 3
                    while retries <= max_retries:
                        try:
                            subject = subject_template.format(**recipient_data, sender=self.email_var.get())
                            message = message_template.format(**recipient_data, sender=self.email_var.get())
                            logging.info(f"Attempting to send email {i+1}/{count} to recipient")
                            self.send_email(server, target, subject, message, attachments)
                            sent_emails += 1
                            self.progress["value"] = sent_emails
                            self.status_label.config(text=f"Sent {sent_emails}/{total_emails} emails")
                            self.root.update()
                            logging.info(f"Sent email {i+1}/{count} to recipient")
                            audit_logger.info(f"Sent email {i+1}/{count} to recipient")
                            last_send_time = time.time()
                            break
                        except Exception as e:
                            retries += 1
                            error_msg = {
                                "SMTPRecipientsRefused": "Recipient refused.",
                                "SMTPDataError": "Server rejected email content. Check subject/message or attachments.",
                                "SMTPServerDisconnected": "Server disconnected. Reconnecting..."
                            }.get(type(e).__name__, f"Error sending to recipient: {str(e)}")
                            logging.warning(f"Retry {retries}/{max_retries} for recipient: {error_msg}")
                            if retries > max_retries:
                                failed_emails.append((target, error_msg))
                                logging.error(f"Failed to send email {i+1}/{count} to recipient: {error_msg}")
                                audit_logger.info(f"Failed to send email {i+1}/{count}: {error_msg}")
                                break
                            time.sleep(2 ** retries)
                            if "disconnected" in error_msg.lower():
                                try:
                                    server.quit()
                                    server = self.create_smtp_connection()
                                    logging.info("Reconnected to SMTP server")
                                    audit_logger.info("Reconnected to SMTP server")
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
            audit_logger.info(f"Email sending completed: {sent_emails}/{total_emails} sent, {len(failed_emails)} failed")
        except Exception as e:
            error_msg = {
                "SMTPAuthenticationError": "Authentication failed. Check email/password or use App Password.",
                "SMTPConnectError": "Failed to connect to SMTP server. Check server/port or try port 465.",
                "SMTPServerDisconnected": "Server disconnected. Try again later or check network."
            }.get(type(e).__name__, f"Failed to send emails: {e}")
            self.show_notification(error_msg, action=self.start_sending)
            logging.error(f"Error: {error_msg}")
            audit_logger.info(f"Email sending failed: {error_msg}")
        finally:
            if server:
                try:
                    server.quit()
                    logging.info("SMTP connection closed")
                    audit_logger.info("SMTP connection closed")
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