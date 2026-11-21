# CardBrowser

The TTSCardMaker card website in its own window, plus three buttons on every card that work with your own copy of
the card files:

- **Open in Photoshop**: opens the card's PSD from your TTSCardMaker folder (Linux: **Open PSD**, in your default app).
- **Show in Finder** / **Explorer** / **folder**: shows the card's PNG in your folder (its PSD is beside it).
- **Copy PNG**: copies the card's PNG from your folder, to paste anywhere (Discord, an image editor, a document).

Everything else (search, card pages, the editor, decks, the rulebook) is the live website, always up to date.

## Download

Get the newest release from the [Releases page](https://github.com/MichaelJSr/CardBrowser/releases):

| Your computer | File |
|---|---|
| Mac with Apple silicon (M1 or newer) | `CardBrowser-<version>-mac-arm64.zip` |
| Mac with an Intel chip | `CardBrowser-<version>-mac-x64.zip` |
| Windows 10 or 11 (64-bit) | `CardBrowser-<version>-windows-x64.zip` |
| Linux | `CardBrowser-<version>-linux.tar.gz` |

Which Mac? Apple menu > About This Mac: "Chip" means Apple silicon, "Processor" means Intel.

## Opening it the first time

CardBrowser is free and not signed with a paid Apple or Microsoft certificate, so each system warns you once.

**macOS** (11 Big Sur or newer)
1. Double-click the zip, then drag `CardBrowser.app` into Applications.
2. Open it. macOS says it can't check it for malware: click Done.
3. Open System Settings > Privacy & Security, scroll down to Security and click **Open Anyway** (it shows for about an
   hour after step 2). Enter your password, then click Open. macOS remembers this.
4. The first time you use a button, macOS asks if CardBrowser may use your Desktop or Documents folder: click Allow.
   Because the app is unsigned, macOS treats each new version as a new app and asks again after every update.

**Windows**
1. Right-click the zip > Properties > tick **Unblock** > OK. Then right-click > Extract All.
2. Open the `CardBrowser` folder and run `CardBrowser.exe`.
3. If "Windows protected your PC" appears: click **More info**, then **Run anyway**.
4. Smart App Control (on some fresh Windows 11 installs) blocks unsigned apps and has no "run anyway". To use
   CardBrowser you would have to turn it off in Windows Security > App & browser control > Smart App Control.
5. CardBrowser needs Microsoft Edge WebView2, which Windows 11 and up-to-date Windows 10 already have. If it is
   missing, CardBrowser says so and opens the download page.

**Linux**
1. Install GTK and WebKit once. Debian/Ubuntu: `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
   gir1.2-webkit2-4.1` (Fedora: `sudo dnf install python3-gobject webkit2gtk4.1`).
2. `tar -xzf CardBrowser-<version>-linux.tar.gz`, then run `./CardBrowser/run.sh`.

## First use

1. Open any card and click one of its buttons.
2. CardBrowser asks for your TTSCardMaker folder: choose the one GitHub Desktop made (often
   `Documents/GitHub/TTSCardMaker`). To change it later: **Choose TTSCardMaker folder…** in the CardBrowser menu.
3. To edit cards on the website, sign in once inside CardBrowser (it keeps its own sign-in, separate from your browser).

## What the messages mean

| Message | What to do |
|---|---|
| Not in your folder yet: pull in GitHub Desktop… | The card is new, renamed or moved and your copy is behind: pull first. |
| Your copy has no linked pictures yet… | Your copy is old: pull, or Photoshop will say links are missing. |
| That folder isn't TTSCardMaker… | Choose the TTSCardMaker folder itself (it has Types and MDW inside). |
| Photoshop not found: opened with your default app. | Photoshop wasn't found, so your usual app for PSD files opened it. |
| macOS blocked CardBrowser from your folder… | Allow it in System Settings > Privacy & Security > Files and Folders. |
| Still working on the last click. / Too many clicks… | Wait a moment, then click again. |
| CardBrowser can't reach this page… | Use **Reload** in the CardBrowser menu (or press F5). |
| …this version of the card site has no file buttons… | The website changed: tell the developers. Searching still works. |
| That didn't work (…) | Try again; if it keeps happening, send the log (**Show log** in the menu). |

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
- **Offline**: the window stays blank. Connect, then use **Reload** in the CardBrowser menu.

## Updates and uninstalling

A note in the corner says when a new version is out; its link opens the release page. Download it and replace the old
app. Your sign-in and folder choice are kept.

To uninstall, delete the app, then (optional) its settings and website data:
- macOS: `~/Library/Application Support/CardBrowser`, `~/Library/WebKit/io.github.michaeljsr.cardbrowser`,
  `~/Library/Caches/io.github.michaeljsr.cardbrowser`
- Windows: `%LOCALAPPDATA%\CardBrowser`
- Linux: `~/.config/CardBrowser`

## For developers

**The site hook** (TTSCardMaker `site/assets/app.js`, `appHook`): each card dialog has an empty `div.card-app` in
`#modal .image-wrap` with `data-file-psd` / `data-file-png` (repo paths with `/`), and openCard fires a `card-dialog`
event on `document` with `detail = {id, psd, png, slot}`. In a browser the slot stays empty and hidden. A page CSP must
allow `'unsafe-eval'` (pywebview builds its bridge with `new Function`). AutoCroissant's `tests/test_site_app_hook.py`
guards the hook.

**Run from source**: `pip install -r requirements.txt -c constraints.txt pytest`, then `python cardbrowser.py`
(tests: `python -m pytest -q tests`).

**Self-test** (ships in every build): `CardBrowser --self-test [--ci] [--report FILE]` runs the real app against a
fixture site and folder on 127.0.0.1 and records the file actions instead of doing them (on macOS run
`CardBrowser.app/Contents/MacOS/CardBrowser`). `--ci` also uses the real clipboard. `--persist write`, then
`--persist read` in a second run with the same `CARDBROWSER_HOME`, checks that the website's sign-in is kept.

**Build**: macOS and Windows: `python packaging/notices.py THIRD-PARTY-NOTICES.txt`, then
`pyinstaller --noconfirm packaging/CardBrowser.spec`. Linux: `packaging/linux.sh`. GitHub Actions
(`.github/workflows/build.yml`) builds every system, self-tests each unpacked build, and on a `v<VERSION>` tag makes a
pre-release. pywebview is pinned to 6.2.1 because `guards.py` patches its internals: a new version must pass
`tests/test_pins.py` and every system's self-test.

**Licence**: CC0 1.0, like TTSCardMaker (`LICENSE`). Bundled software and its licences: `THIRD-PARTY-NOTICES.txt`.
