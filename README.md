![image](https://github.com/user-attachments/assets/fac5013a-2b16-43d9-8a14-3e1959e8f961)


---

**ShurikenMail** is a GUI-based Python tool for sending bulk emails during authorized phishing tests. It supports encrypted logs, PIN protection, attachments, and recipient CSV imports.

---

## Installation

```bash
git clone https://github.com/calebpentest/SHURIKENMAIL.git
cd SHURIKENMAIL
pip install cryptography keyring
```

For Linux keyring support:
```bash
sudo apt-get install python3-dbus gnome-keyring
```

---

## ▶️ Run the App

```bash
python shurikenmail.py
```

- **Default PIN:** `1234`  
- **Reset PIN:**  
  ```bash
  python -c "import keyring; keyring.delete_password('ShurikenMail', 'app_pin')"
  ```

- **Reset Logs (if decryption fails):**  
  ```bash
  python -c "import keyring; keyring.delete_password('ShurikenMail', 'fernet_key')"
  ```

Then delete `shurikenmail_log.enc` and restart the app.

---

For ethical use only [👉] always get authorization before sending.  

---
