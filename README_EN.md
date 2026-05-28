# Soundpad Helper

> 🌐 Remote control Soundpad on Windows via a web interface
>
> [中文](README.md)

A lightweight LAN remote controller — start the server on your PC, then open the web page from your phone or any device's browser to remotely trigger sound effects, manage audio categories, and save custom controls.

![Web UI Screenshot](images/web-ui.png)

---

## ✨ Features

- **📋 Sound Sync** — Automatically loads the Soundpad audio list and displays it in a categorized tree
- **🎵 One-Click Play** — Supports direct playback via Soundpad's Named Pipe API (preferred) and keyboard hotkey simulation (fallback)
- **🗂️ Collapsible Categories** — Accordion navigation for groups and subgroups, collapsed by default, auto-expands on search
- **🔍 Real-Time Search** — Filter sounds instantly by keyword
- **➕ Custom Controls** — Add / edit / delete custom shortcut buttons
- **🌗 Light & Dark Theme** — Dark theme by default, one-click toggle, preference persisted locally
- **📱 Responsive Layout** — Adapts to phone / tablet / desktop, adjustable columns per row (1–6)
- **💾 Persistent Config** — Control layouts saved to server `config.json`, also supports `localStorage`

---

## 🚀 Quick Start

### Prerequisites

- **Windows** OS
- **Python 3.7+**
- [Soundpad](https://leppsoft.com/soundpad/) (paid software, must be installed and running)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yuanfang1120/soundpad_web.git
cd soundpad_web/lib

# 2. Install dependencies
pip install -r requirements.txt
```

Or double-click `安装依赖.bat` to install dependencies.

### Run

```bash
cd lib
python server.py
```

Or double-click `启动server.bat`.

Once started, the terminal will print all local IP addresses. Open `http://<IP>:11451` in your phone's browser.

### SPL File Setup

In Soundpad, go to **File → Save Sound List As "音频路径.spl"**, then place the `.spl` file in the program directory:

![SPL File Path](images/spl-path.png)

---

## 📐 How It Works

```
┌──────────────┐     HTTP/WebSocket      ┌──────────────┐
│  Phone/Tablet │ ◄────────────────────► │  Python Server │
│  (Browser)    │     LAN                │  (Flask)       │
└──────────────┘                          └──────┬───────┘
                                                 │
                                   ┌─────────────┴─────────────┐
                                   │                           │
                          Preferred ↓                   Fallback ↓
                        Named Pipe API            Keyboard Simulation
                   \\.\pipe\sp_remote_control     (pynput: Alt+Numpad)
                                   │                           │
                                   └─────────────┬─────────────┘
                                                 │
                                        ┌────────┴────────┐
                                        │    Soundpad     │
                                        │  (Windows App)  │
                                        └─────────────────┘
```

| Strategy   | Method               | Description                                                      |
|------------|----------------------|------------------------------------------------------------------|
| **Primary** | Named Pipe API      | Direct communication with Soundpad via `\\.\pipe\sp_remote_control` |
| **Fallback** | Keyboard Simulation | Simulates `Alt + Numpad` key combos to trigger Soundpad hotkeys   |

---

## 🔧 API Reference

| Route          | Method | Parameters          | Description                                         |
|----------------|--------|---------------------|-----------------------------------------------------|
| `/`            | GET    | —                   | Serve the web frontend                              |
| `/heartbeat`   | GET    | —                   | Health check, returns `{"status":"alive"}`          |
| `/sync_sounds` | GET    | —                   | Sync audio list (pipe preferred → SPL fallback)    |
| `/play_sound`  | POST   | `{"index": "0"}`    | Play a sound via the pipe API                       |
| `/stop_sound`  | POST   | —                   | Stop playback via the pipe API                      |
| `/keyboard`    | POST   | `{"key": "123"}`    | Keyboard simulation (Alt + digit sequence)          |
| `/stop`        | POST   | —                   | Keyboard simulation stop (Alt+0)                    |
| `/save_config` | POST   | JSON body           | Save control layout config                          |
| `/load_config` | GET    | —                   | Load control layout config                          |

---

## 📁 Project Structure

```
soundpad_web/
├── images/
│   ├── web-ui.png           # Web UI screenshot
│   └── spl-path.png         # SPL file path screenshot
├── lib/
│   ├── server.py            # Flask main program (API + pipe + SPL parsing)
│   ├── requirements.txt     # Python dependencies
│   ├── config.json          # Control layout config (auto-generated)
│   ├── test.py              # Keyboard listener debug script
│   ├── 启动server.bat        # Windows launcher script
│   ├── 安装依赖.bat          # Windows dependency installer
│   ├── 音频路径.spl          # Soundpad project file (sound list + categories)
│   └── web/
│       └── index.html       # Single-page web app (full remote UI)
├── .gitignore
├── LICENSE
├── README.md                # 中文 README
└── README_EN.md             # English README
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## ⚠️ Disclaimer

This is a third-party tool and is not affiliated with [Leppsoft Soundpad](https://leppsoft.com/soundpad/). Soundpad is commercial software by Leppsoft — please obtain it through official channels.
