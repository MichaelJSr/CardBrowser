# CardBrowser

The TTSCardMaker card website in its own window, plus three buttons on every card that work with your own copy of
the card files:

- **Open in Photoshop**: opens the card's PSD from your TTSCardMaker folder.
- **Show in Finder** / **Explorer**: shows the card's PNG in your folder (its PSD is beside it).
- **Copy PNG**: copies the card's PNG from your folder, to paste anywhere (Discord, an image editor, a document).

Everything else (search, card pages, decks, the rulebook, stats, people) is the live website, always up to date.

**CardBrowser is read-only**: no Sign in, no Edit, and no sign-in, token or key kept (a private deck asks for its
passphrase each time). Edit cards, the rulebook, your profile or decks on the website in your browser: **Open this page
in my browser** in the CardBrowser menu opens the same page there.

## Download

Get the newest release from the [Releases page](https://github.com/MichaelJSr/CardBrowser/releases):

| Your computer | File |
|---|---|
| Mac with Apple silicon (Apple menu > About This Mac says "Chip") | `CardBrowser-<version>-mac-arm64.zip` |
| Mac with an Intel chip (About This Mac says "Processor") | `CardBrowser-<version>-mac-x64.zip` |
| Windows 10 or 11 (64-bit) | `CardBrowser-<version>-windows-x64.zip` |

Linux is not supported yet.

## Opening it the first time

CardBrowser is free and not signed with a paid Apple or Microsoft certificate, so each system warns you once.

**macOS** (11 Big Sur or newer)
1. Double-click the zip, then drag `CardBrowser.app` into Applications.
2. Open it. macOS says it can't check it for malware (or can't verify the developer): close that message.
3. macOS 15 or newer: open System Settings > Privacy & Security, scroll down to Security and click **Open Anyway** (it
   shows for about an hour after step 2), enter your password, then click Open. macOS 11-14: Control-click the app in
   Applications, choose Open, then click Open. macOS remembers this.
4. The first time you use a button, macOS asks if CardBrowser may use your Desktop or Documents folder: click Allow.
   Because the app is unsigned, macOS treats each new version as a new app and asks again after every update.

**Windows**
1. Right-click the zip > Properties > tick **Unblock** > OK. Then right-click > Extract All.
2. Open the `CardBrowser` folder and run `CardBrowser.exe`.
3. If "Windows protected your PC" appears: click **More info**, then **Run anyway**.
4. Smart App Control (some fresh Windows 11 installs) blocks unsigned apps with no "run anyway": turn it off to use it.
5. CardBrowser needs Microsoft Edge WebView2 (Windows 11 and up-to-date Windows 10 have it); if not, it says so.

## First use

1. Open any card and click one of its buttons.
2. CardBrowser asks for your TTSCardMaker folder: choose the one GitHub Desktop made (often
   `Documents/GitHub/TTSCardMaker`). To change it later: **Choose TTSCardMaker folder…** in the CardBrowser menu.

## What the messages mean

| Message | What to do |
|---|---|
| Not in your folder yet: pull in GitHub Desktop… | The card is new, renamed or moved and your copy is behind: pull first. |
| Your copy has no linked pictures yet… | Your copy is old: pull, or Photoshop will say links are missing. |
| That folder isn't TTSCardMaker… | Choose the TTSCardMaker folder itself (it has Types and MDW inside). |
| Photoshop not found: opened with your default app. | Photoshop wasn't found, so your usual app for PSD files opened it. |
| macOS blocked CardBrowser from your folder… | Allow it in System Settings > Privacy & Security > Files and Folders (macOS 11-12: System Preferences > Security & Privacy > Privacy). |
| Still working on the last click. / Too many clicks… | Wait a moment, then click again. |
| CardBrowser can't reach this page… | Use **Reload** in the CardBrowser menu (or press F5). |
| …this version of the card site has no file buttons… | The website changed: tell the developers. Searching still works. |
| That didn't work (…) | Try again; if it keeps happening, send the log (**Show log** in the menu). |
| Windows blocked CardBrowser's files… (0.1.1: Failed to resolve Python.Runtime.Loader.Initialize) | Move the `CardBrowser` folder to a folder on this computer, or download it again and **Unblock** the zip before extracting (Windows step 1). |

## What CardBrowser never does

- Change, move or delete any file (it only opens, shows and copies card files from your folder).
- Run git, commit or push: you keep using GitHub Desktop.
- Send your folder's location anywhere: it stays in CardBrowser's settings on your computer.
- Install fonts, hooks or anything else.

## Known limits

- **Printing proxies**: in the deck, choose Copy share link, open that link in your browser and print there (or use
  **Open this page in my browser** in the CardBrowser menu).
- **Dragging the card file**: click Show, then drag the file from your file manager. Dragging the picture on the page
  drags the website's copy.
- **Offline**: the window stays blank (Windows: an error page). Connect, then use **Reload** in the CardBrowser menu.

## Updates and uninstalling

A note in the corner says when a new version is out; its link opens the release page. Download it and replace the old
app. Your folder choice and the website's settings in CardBrowser (theme, filters, hands) are kept.

To uninstall, delete the app, then (optional) its settings and website data:
- macOS: `~/Library/Application Support/CardBrowser`, `~/Library/WebKit/io.github.michaeljsr.cardbrowser`,
  `~/Library/Caches/io.github.michaeljsr.cardbrowser`
- Windows: `%LOCALAPPDATA%\CardBrowser`

## For developers

**The site hook** (TTSCardMaker `site/assets/app.js`): each card dialog has an empty `div.card-app` in `#modal
.image-wrap` with `data-file-psd` / `data-file-png` (repo paths), and openCard fires `card-dialog` on `document` with
`detail = {id, psd, png, slot}`; a browser shows nothing. Before the site's scripts CardBrowser sets a frozen
`window.cardApp = {readOnly: true}` (`guards.py` START), so `appReadOnly()` leaves out Sign in, Edit and the editor.
START also stops pages keeping WebCrypto keys in IndexedDB (macOS would seal them with a keychain key that asks for the
Mac password after each update). If START cannot be added, no site page loads. A page CSP must allow `'unsafe-eval'`
(pywebview's bridge uses `new Function`). No untrusted HTML in any frame. AutoCroissant's `tests/test_site_app_hook.py`
guards all of this.

**Self-test** (in every build): `CardBrowser --self-test [--ci] [--report FILE]` runs the real app, window hidden,
against a fixture site and folder on 127.0.0.1, recording the file actions (macOS: run
`CardBrowser.app/Contents/MacOS/CardBrowser`). `--ci` also uses the real clipboard. `--persist write`, then `--persist
read` in a second run with the same `CARDBROWSER_HOME`, checks that the website's saved data is kept.

**Build**: from source, `pip install -r requirements.txt -c constraints.txt pyinstaller pytest` (tests: `python -m
pytest -q tests`), then `python packaging/notices.py THIRD-PARTY-NOTICES.txt` and `pyinstaller --noconfirm
packaging/CardBrowser.spec`. GitHub Actions (`.github/workflows/build.yml`) builds macOS and Windows, self-tests each
unpacked build (Windows: also a copy marked as downloaded; macOS: `packaging/minos.py` checks that no part needs a newer
macOS than 11), and on a `v<VERSION>` tag makes a pre-release. pywebview is pinned to 6.2.1 because `guards.py` patches
its internals: a new version must pass `tests/test_pins.py` and both systems' self-tests.

**Icon**: the game's logo as on the rulebook cover. `python packaging/icon/make_icon.py <Half_Holder.jpg>` (TTSCardMaker
`MDW/Assets/Holders/`) rebuilds `packaging/icon/CardBrowser.icns` (on a Mac) and `CardBrowser.ico`.

**Licence**: CC0 1.0, like TTSCardMaker (`LICENSE`). Bundled software and its licences: `THIRD-PARTY-NOTICES.txt`.
