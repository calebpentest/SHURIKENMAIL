# ShurikenMail

ShurikenMail is a Python-based desktop application for sending bulk emails with a user-friendly GUI, built using Tkinter. It supports SMTP configuration, CSV recipient imports, email previews, attachments, and encrypted logging for secure and efficient email campaigns.

## Features
- **SMTP Configuration**: Supports Gmail, Yahoo, Outlook, and custom SMTP servers with secure password storage via keyring.
- **Bulk Email Sending**: Send emails to multiple recipients with customizable message counts (1–100 per recipient).
- **Recipient Management**: Load recipients manually or via CSV files with email validation.
- **Email Content**: Format messages with placeholders (e.g., `{name}`, `{sender}`) and attach files (up to 25MB).
- **Preview & Testing**: Preview email content with HTML support and send test emails to verify setup.
- **Spam Detection**: Analyzes content for spam triggers to improve deliverability.
- **Encrypted Logging**: Logs actions securely with Fernet encryption and a rotating file handler.
- **Theming**: Toggle between light and dark modes for better usability.
- **Ethical Use**: Requires user consent to ensure responsible emailing.

## Requirements
- Python 3.7+
- Required libraries: `tkinter`, `smtplib`, `keyring`, `requests`, `cryptography`, `email`
- Install dependencies:
  ```bash
  pip install cryptography keyring requests
Installation
Clone the repository:
bash
```
git clone https://github.com/calebpentest/SHURIKENMAIL.git
cd SHURIKENMAIL
```
Install dependencies (see above).
Run the application:
bash
python shurikenmail.py
Usage
SMTP Settings: Enter your SMTP server, port, email, and password (saved securely via keyring).
Email Content: Input recipient emails (manually or via CSV), subject, message, and optional attachments.
Preview: Use the Preview tab to review formatted emails (Ctrl+P).
Test Send: Send a test email to your address to verify settings.
Send Emails: Confirm ethical use, then click "Send Emails" (Ctrl+Enter) to start sending.
Logs: View encrypted logs by entering the Fernet key (stored in shurikenmail_config.json).

Notes
Attachments: Files >20MB should be hosted on Google Drive due to size limits.
App Passwords: For Gmail, use an App Password if 2FA is enabled.
Logs: Encrypted logs are stored in shurikenmail_log.enc with a 1MB size limit and 5 backups.
Configuration: Settings are saved in shurikenmail_config.json.
License
MIT License
Disclaimer
Use ShurikenMail responsibly and comply with anti-spam laws (e.g., CAN-SPAM Act). The developers are not liable for misuse.
