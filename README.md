<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.7%2B-blue?logo=python&logoColor=white">
  <img alt="License" src="https://img.shields.io/github/license/CyberSheeple/CTFdScraper?color=blueviolet">
  <img alt="Stars" src="https://img.shields.io/github/stars/CyberSheeple/CTFdScraper?style=social">
  <img alt="Last Commit" src="https://img.shields.io/github/last-commit/CyberSheeple/CTFdScraper">
  <img alt="Issues" src="https://img.shields.io/github/issues/CyberSheeple/CTFdScraper">
<img alt="PRs" src="https://img.shields.io/github/issues-pr/CyberSheeple/CTFdScraper">
</p>


# 🕵️‍♂️ CTFd Challenge Scraper

A simple Python 3 tool to automatically download challenges and files from any CTFd instance.

Supports:
- Session cookie authentication **or** username/password login
- `.env` or CLI-based usage
- Downloads challenge descriptions and files
- Skips existing files if needed

---

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/CyberSheeple/CTFdScraper.git
cd CTFdScraper

# Set up a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
````

---

## ⚙️ Configuration

You can either use a `.env` file **or** pass arguments via the command line.

### Option 1: Using `.env`

Create a `.env` file in the root folder:

```
SESSION=your_session_cookie              # OR use USERNAME + PASSWORD below
USERNAME=your_username
PASSWORD=your_password
URL=https://your-ctfd-url.com
```

Then simply run:

```bash
python3 main.py
```

---

### Option 2: Using command-line args

```bash
python3 main.py \
  --username your_username \
  --password your_password \
  --url https://your-ctfd-url.com
```

Or with a session cookie:

```bash
python3 main.py \
  --session your_session_cookie \
  --url https://your-ctfd-url.com
```

---

## 🧰 Extra Options

* `--nofiles` – Skip downloading files, just save challenge descriptions.
* `--nooverwrite` – Don't overwrite existing `description.md` files.

---

## 📁 Output Structure

All content will be saved under the `output/` directory like this:

```
output/
└── category/
    └── challenge_name/
        ├── description.md
        └── challenge_file.ext
```

---

## 📦 Requirements

* Python 3.7+
* Libraries in `requirements.txt`:

  * `requests`
  * `beautifulsoup4`
  * `python-dotenv`

---

## 🙏 Credits

Made for automation lovers & CTF enthusiasts.
Feel free to fork and adapt for your own CTF team setup!

---
