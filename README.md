# SnapShotter — Accounting Edition

A Windows screenshot tool for accountants who capture evidence for workpapers: account reconciliations, journal entry support, audit requests and close work.

Snipping Tool takes the picture. SnapShotter also proves **when** it was taken, names it so you can **find** it, and keeps a **record** of it.

## Features

- **Taskbar clock in every capture**: the Windows taskbar (with the date/time) is included in, or attached to, each image as a visible time stamp. If the taskbar is auto-hidden, a capture-time bar is stamped on instead.
- **Workpaper labels in the file name**: entity, account, period and JE/ticket reference, with a live preview of the file name before you capture.
- **Evidence index**: every capture is logged to `evidence_index.csv` in the save folder.
- **Saved folders**: keep a drop-down list of client or engagement folders; screenshots go straight into the chosen folder.
- **Capture from any app**: `Ctrl + Shift + F9` (configurable) works while you're in Excel, your ERP or a browser. `F9` works inside SnapShotter.
- **Copy to clipboard**: paste straight into Excel, Word or email with `Ctrl+V`.
- **Nothing interrupts you**: after a capture a small preview appears in the corner with Mark up, Show in folder and Undo, then disappears on its own.
- **It remembers**: entities, accounts, references and folders you've used are one click away.
- **Highlight, box and redact markup**: the original is never changed; the marked-up version is saved as `…_marked.png` and indexed with the same labels.
- **Capture modes**: area (drag to select), one screen, all screens, or one image per screen.

## Install (Windows)

1. Install Python 3.10+ from <https://www.python.org/downloads/> and tick **Add Python to PATH**.
2. Download this repository (**Code → Download ZIP**) and extract it.
3. Double-click `install.bat` once.
4. Double-click `run.bat` to start SnapShotter.

### Can't run .bat files? (common on work computers)

Run it from PyCharm, VS Code or any Python you're allowed to use:

1. Open the folder as a project and pick a Python 3.10+ interpreter.
2. Run `snapshotter.py`.
3. On first run SnapShotter offers to install its two packages (mss and Pillow). Click **Yes**; no admin rights needed.

Or install them yourself in PyCharm's **Terminal** tab: `python -m pip install -r requirements.txt`

See [README.txt](README.txt) for the full user guide.

## Note

The PNGs and CSV index are a convenience, not a tamper-proof audit trail. Follow your organization's evidence retention and access policies.
