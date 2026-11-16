SNAPSHOTTER — ACCOUNTING EVIDENCE CAPTURE
=========================================

A familiar, Snipping Tool-style screenshot app with extra organization
for account reconciliations, journal entries, audit requests, and close work.

INSTALL
-------
1. Install Python 3.10 or newer from https://www.python.org/downloads/
   During setup, enable "Add Python to PATH".
2. Extract this ZIP to a folder.
3. Double-click install.bat once.
4. Double-click run.bat whenever you want to use SnapShotter.

CAN'T RUN .BAT FILES? (work computers)
--------------------------------------
Run snapshotter.py from PyCharm, VS Code or any Python you're allowed
to use (File > Open the folder, choose a Python 3.10+ interpreter, then
right-click snapshotter.py > Run). The first time, SnapShotter offers to
install mss and Pillow for you; click Yes. No admin rights are needed.
If that fails, run this in PyCharm's Terminal tab:
    python -m pip install -r requirements.txt
A connection/SSL error usually means the company network blocks the
Python package site: ask IT for the proxy or internal package mirror.

HOW IT WORKS (v5.0)
-------------------
1. Label (optional): entity, period, account, JE/ticket ref. Each box
   remembers what you've used before; pick it from the drop-down.
   "Will be saved as" shows the exact file name.
2. Capture: choose Area, One screen, All screens or Each screen, then
   click Capture, press F9, or press Ctrl+Shift+F9 from any app.
3. Paste: the screenshot is already on the clipboard. Ctrl+V in Excel.

After every capture a small preview appears in the bottom-right corner.
It never needs a click and disappears on its own. From it you can:
  - Mark up: highlight, box or redact (also: click the picture)
  - Show in folder
  - Undo: deletes that screenshot and removes it from the index

Save to: folders you use are remembered in the drop-down automatically.
Recent: select a file to see a preview, then Open / Mark up / Copy /
Show in folder.
Settings (top right): shortcut key, copy to clipboard, taskbar clock,
open after capture, filename prefix.

If evidence_index.csv is open in Excel when you capture, nothing fails:
the screenshot is saved and the index is updated once you close it.

Redact: draws a solid black box in the marked copy. The original
screenshot is always kept unredacted next to it, so share the _marked
file, not the original, when something must stay hidden.

WHERE FILES GO
--------------
Default folder: Documents\Accounting Evidence

Screenshots are saved directly in the folder you choose. No subfolders
are created.

An evidence_index.csv file is maintained in the save folder.
It records capture time, entity, account, period, reference,
capture mode, display/region, and filename. (The work_type column is
kept blank so older index files stay lined up.)

The CSV is a convenience index, not a tamper-proof audit trail. Follow
your organization's retention, access, confidentiality, and evidence
handling policies. Avoid putting sensitive data in labels or
filenames if your policy prohibits it.

CUSTOM SAVE FOLDERS (v3.2)
--------------------------
The save-folder box in step 3 is a drop-down of your saved folders.
  - Browse… to a folder (or capture into one) and it is added for you.
  - Pick any saved folder from the drop-down to switch to it.
  - "Remove this folder from the list" only removes it from the drop-down; nothing on disk
    is deleted.
  - Filename prefix (optional, in ⚙ Settings) is put at the start of each file name,
    e.g. Screenshot_2026-11-15_09-51-02_2026-11_Region.png
Your folders, the last folder used, the prefix, and the checkbox choices are
remembered between sessions in %APPDATA%\SnapShotter\settings.json.
Each folder keeps its own evidence_index.csv.

TASKBAR TIME STAMP (v3.2)
-------------------------
With "Include the taskbar (date/time clock) in every screenshot" ticked
(the default), each image shows the Windows taskbar so the system clock
is visible as a time stamp:
  - Rectangular areas: the taskbar of the screen you captured is added
    beneath the selection (beside it if your taskbar is on the left/right).
  - One monitor / each monitor: if that monitor has its own taskbar it is
    already in the shot; otherwise the main taskbar is added beneath.
  - The image and the taskbar come from the same instant, so the clock
    matches the moment of capture. (Rectangular captures now use the frozen
    screen shown while you drag, like Snipping Tool.)
  - If the taskbar is set to auto-hide, there is no clock on screen to
    capture. SnapShotter then adds a dark bar with the capture date/time
    instead. Turn off auto-hide (Settings > Personalization > Taskbar >
    Taskbar behaviors) if you want the real taskbar clock in every shot.
  - The CSV index notes "+ taskbar" or "+ time stamp" in display_or_region.

SHORTCUTS (v3.4)
----------------
Ctrl + Shift + F9 captures from ANY app (Excel, your ERP, a browser...)
as long as SnapShotter is open; it can stay minimized. It uses whatever
capture mode, folder and workpaper labels are currently set.
  - Change it in ⚙ Settings > "Shortcut from any app" (or choose Off).
  - If the status says the shortcut is in use by another program, pick
    a different one from the list.
  - After a shortcut capture SnapShotter stays out of the way: a small
    notice appears in the bottom-right corner instead of a pop-up.
F9 still works inside the SnapShotter window.
In a rectangular capture, Esc or right-click cancels.

COPY TO CLIPBOARD (v3.4)
------------------------
With "Copy to clipboard" ticked (default), each capture is also copied,
so you can press Ctrl+V straight into an Excel workpaper, Word or email.
If you marked it up, the marked-up version is what's copied.
"Each monitor separately" makes several images, so nothing is copied.

HIGHLIGHT AND BOX (v3.4)
------------------------
Tick "Mark up after capture" to open the markup window after each
capture, or select any file under Recent evidence and click
"🖍 Mark up".
  - Highlight: drag to put a see-through yellow highlight over a row
    or amount.
  - Box: drag to draw an outlined box (red, blue, green or black).
  - Ctrl+Z undoes, Enter saves, Esc skips.
The original screenshot is never changed. The markup is saved as a
separate copy named ..._marked.png next to it, and gets its own line in
evidence_index.csv with the same workpaper labels.

NOTES
-----
- Captures are saved as PNG files.
- Date/time in file names uses your computer's local time.
- Existing files are never overwritten; a numeric suffix is added.
- Monitor detection and capture use MSS.


The main window includes an 'Open Screenshot Save Folder' button near the top. It opens the currently selected save location in Windows File Explorer.

WINDOW SIZE (v3.5)
------------------
If your screen is too short to show everything (small laptop screen or
display scaling), a scrollbar appears on the right. Scroll down with the
mouse wheel to reach the lower sections.
