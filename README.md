# CardBrowser

The TTSCardMaker card website in its own window, with three buttons on every card that use your own copy of the card
files: **Open in Photoshop**, **Show in Finder/Explorer** and **Copy PNG**. It is read-only: to edit, use **Open this
page in my browser** in its menu.

## Download

From [Releases](https://github.com/MichaelJSr/CardBrowser/releases): `mac-arm64` (Apple silicon), `mac-x64` (Intel)
or `windows-x64` (Windows 10/11).

## First open

The app is unsigned, so each system warns once.

- **macOS 11+**: drag `CardBrowser.app` into Applications, open it and close the warning. Then macOS 15+: System
  Settings > Privacy & Security > **Open Anyway**; macOS 11-14: Control-click the app > Open.
- **Windows**: right-click the zip > Properties > **Unblock**, then Extract All and run `CardBrowser.exe` (**More
  info** > **Run anyway** if asked). It needs Microsoft Edge WebView2.

At the first button click, choose your TTSCardMaker folder (often `Documents/GitHub/TTSCardMaker`).

## Trouble

- **Not in your folder yet** or **no linked pictures**: pull in GitHub Desktop.
- **macOS blocked CardBrowser from your folder**: allow it in Privacy & Security > Files and Folders.
- **Windows: could not load its Windows parts** (0.1.1: *Failed to resolve Python.Runtime.Loader.Initialize*): get
  0.1.2 or newer, or Unblock the zip and extract it again.
- Anything else: send the developers the log (**Show log** in the menu).

CardBrowser never changes your files, runs git or sends your folder's location anywhere. Updates: replace the app
(settings are kept).

## Developers

`pip install -r requirements.txt -c constraints.txt pyinstaller pytest`, `python -m pytest -q tests`, `python
packaging/notices.py THIRD-PARTY-NOTICES.txt`, `pyinstaller --noconfirm packaging/CardBrowser.spec`. CI builds and
self-tests each system; a `v<VERSION>` tag makes a pre-release. AutoCroissant's `tests/test_site_app_hook.py` guards the
site hook. pywebview stays pinned: `guards.py` patches it. Licence CC0 1.0 (`THIRD-PARTY-NOTICES.txt` for bundled
software).
