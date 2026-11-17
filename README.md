<div align="center">

<h1>🖨️ Gmail Attachment Printer</h1>

<p>
  <strong>Automated unread Gmail attachment monitor &amp; cross-platform desktop printer</strong>
</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/GUI-Tkinter-4B8BBE?style=for-the-badge" alt="Tkinter GUI" />
  <img src="https://img.shields.io/badge/API-Gmail%20v1-EA4335?style=for-the-badge&logo=gmail&logoColor=white" alt="Gmail API v1" />
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-2D3748?style=for-the-badge" alt="Windows | macOS | Linux" />
</p>

<p>
  <a href="#-features">Features</a> •
  <a href="#-setup--installation">Setup</a> •
  <a href="#%EF%B8%8F-configuration-options">Configuration</a> •
  <a href="#%EF%B8%8F-platform-printing-behavior">Printing</a> •
  <a href="#%EF%B8%8F-troubleshooting">Troubleshooting</a>
</p>

</div>

---

A lightweight desktop application built with Python and Tkinter that monitors your Gmail inbox for unread emails with attachments and automatically sends supported documents to your default printer.

## ✨ Features

- **Manual & Scheduled Checking** — Trigger a check anytime with **Check Gmail now**, or set an automatic polling interval from **60 seconds** up to **10 hours**.
- **Smart Unread Handling** — Scans unread emails with attachments (`is:unread has:attachment`) and only marks a message as read after its eligible attachments have been printed successfully. Emails with unsupported attachments or print errors stay unread.
- **Supported File Types** — Filters attachments to `.pdf`, `.png`, `.jpg`, `.jpeg`, and `.docx`.
- **Flexible Storage Mode** — Use **Don't save file** (enabled by default) to print from temporary files, or uncheck it to archive printed attachments locally in an `attachments/` folder.
- **Cross-Platform Printing** — Supports **Windows** (with silent printing via SumatraPDF or Windows shell fallback), **macOS**, and **Linux** (via CUPS `lp`).
- **Virtual Printer Protection (Windows)** — Detects if the Windows default printer is a virtual file-output printer (`Microsoft Print to PDF`, `Microsoft XPS Document Writer`, `OneNote`) and prevents accidental non-physical print jobs.
- **Live Activity Log** — Thread-safe GUI log viewer and console output for real-time status, OAuth prompts, and error reporting.
- **Persistent Settings** — Automatically saves preferences to `settings.json`.

---

## 📋 Requirements

- **Python 3.10+** (with `tkinter` installed)
- **Google Cloud Project** with the **Gmail API** enabled and a **Desktop app** OAuth 2.0 client JSON (`credentials.json`)
- **Dependencies:**
  - `google-api-python-client`
  - `google-auth-oauthlib`
  - `google-auth`

> [!NOTE]
> On some Linux distributions, Tkinter is packaged separately. If needed, install it with your system package manager (for example, `sudo apt install python3-tk`).

---

## 🚀 Setup & Installation

### 1. Configure Gmail API Credentials
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project and enable the **Gmail API**.
3. Configure the **OAuth consent screen** and add your Gmail address as a test user if the app is in testing mode.
4. Go to **Credentials → Create Credentials → OAuth client ID** and choose **Desktop app**.
5. Download the JSON file, rename it to `credentials.json`, and place it in the same directory as `main.py`.

### 2. Install Python Dependencies
```bash
pip install poetry
```
```bash
poetry install
```

### 3. Run the Application
```bash
python main.py
```

On the first Gmail check, your browser will open to complete the Google OAuth consent flow (using the `https://www.googleapis.com/auth/gmail.modify` scope). Once authorized, `token.json` is saved beside `main.py` and refreshed automatically on future runs.

---

## ⚙️ Configuration Options

All settings in the GUI are persisted automatically to `settings.json`:

| Setting | Options | Default |
| :--- | :--- | :--- |
| **Operating system** | `Windows`, `macOS`, `Linux` | `Windows` |
| **Automatic check interval** | `Disabled (never checks)`, `60 sec`, `5 min`, `10 min`, `20 min`, `30 min`, `1 hour`, `2 hours`, `5 hours`, `10 hours` | `Disabled (never checks)` |
| **Don't save file** | Checked (temporary files) / Unchecked (save to `attachments/`) | Checked (`true`) |

### Supported Attachment Extensions
`main.py` processes attachments matching these extensions:
- `.pdf`
- `.docx`

Optional attachments matching these extensions can be selected:
- `.png`
- `.jpg`
- `.jpeg`

---

## 🖨️ Platform Printing Behavior

### Windows
- Checks your default Windows printer via PowerShell (`Get-CimInstance Win32_Printer`).
- Rejects virtual file printers (`Microsoft Print to PDF`, `Microsoft XPS Document Writer`, `OneNote`) so jobs are only sent to a physical printer.
- **SumatraPDF (Recommended):** If `SumatraPDF.exe` is found on `PATH` or in `%ProgramFiles%\SumatraPDF\` / `%LOCALAPPDATA%\SumatraPDF\`, the app uses `SumatraPDF.exe -silent -print-to-default` for silent printing.
- **Shell Fallback:** If SumatraPDF is not installed, `os.startfile(..., "print")` is used. Because Windows shell print verbs are asynchronous, temporary files are scheduled for deletion after **10 minutes** so the registered viewer has time to finish reading the file.

### macOS & Linux
- Uses the standard CUPS `lp` command (`lp <file>`).
- Ensure a default printer is configured in CUPS and that `lp` is available on your `PATH`.

---

## 📁 Project Files

```text
.
├── main.py             # Application entry point, GUI, Gmail polling, and printing logic
├── credentials.json    # (User-provided) Google OAuth Desktop client secrets
├── token.json          # (Auto-generated) Cached Gmail OAuth access/refresh token
├── settings.json       # (Auto-generated) Saved GUI preferences
└── attachments/        # (Auto-generated when "Don't save file" is unchecked) Saved files
```

> [!IMPORTANT]
> Keep `credentials.json` and `token.json` private and never commit them to version control.

---

## 🛠️ Troubleshooting

- **`credentials.json is missing` warning on startup:** Place your downloaded Google Cloud OAuth client file as `credentials.json` in the same folder as `main.py`.
- **`The Windows default printer is '...', a file-output printer`:** Set a physical printer as your default printer in Windows Settings.
- **`The 'lp' command was not found` (macOS/Linux):** Install and configure CUPS and verify that `lp` works from your terminal.
- **Emails stay unread after a check:** Either the email had no attachments with an allowed extension (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.docx`), or printing failed. Check the GUI log panel for details.