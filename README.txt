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

WORKFLOW (v4.0 layout)
----------------------
1  Label this evidence: entity, period, account, JE/ticket ref (all
   optional). "File name:" shows exactly what the file will be called.
   Labels stay filled in for the next capture; "Clear labels" resets them.
2  Capture: click a tile (Area, One screen, All screens, Each screen).
   The display picker only appears for One screen. Tick "Mark up after
   capture" / "Copy to clipboard", pick a Delay if needed, then click the
   big Capture button, press F9, or press Ctrl+Shift+F9 from any app.
3  Save to: pick a folder from the drop-down. Browse… for a new one,
   "Keep in list" to remember it, "Open folder" to see it in Explorer.
Recent evidence: select a file, then Open / Mark up / Copy / Show in
folder. Marked-up copies show a 🖍 in the list.

The ⚙ Settings button (top right) holds the set-once options:
shortcut key, filename prefix, include taskbar clock, open after capture.
The note at the top right shows whether the any-app shortcut is active
(green) or unavailable (orange). Hover over any button for a tip.

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
  - Browse… (or type a path), then click "★ Keep in list" to add it.
  - Pick any saved folder from the drop-down to switch to it.
  - "Remove from list" only removes it from the drop-down; nothing on disk
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
