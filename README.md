# Ghost Trader

A local Linux desktop app for running a "ghost" (paper) options portfolio on TQQQ. It covers covered calls,
cash-secured puts, and share buys and sells. You make every trade decision; the app keeps the books.

- **Quotes:** real chains from Yahoo Finance via `yfinance` (about 15 minutes delayed). The 3-month T-bill rate
  comes from Alpha Vantage (your key goes in Settings), then `^IRX` via Yahoo, then a manual rate.
- **Ledger:** a SQLite file at `~/.local/share/ghost-trader/ledger.db`, backed up at every startup and before
  every update (the last 30 backups are kept).
- **Window:** the app opens its own native window (pywebview + WebKitGTK). If that fails it falls back to
  Chromium, and to Firefox only after asking you.

## Rules the app enforces

- **Allowed trades:** covered calls and cash-secured puts only.
- **Puts:** a put's collateral (strike × 100) comes out of cash you already have. The trade's own premium
  doesn't count toward it, but the premium is spendable right away.
- **Fill price:** must be between the bid and the ask, with no override. Sells default to the mid; buys default
  halfway between the mid and the ask.
- **Mistakes:** every trade has a confirm step, and there's no undo. To fix a mistake, trade the opposite way;
  History shows both trades.
- **Expirations:** options are settled at the first startup after 5 PM Central on expiration day. Anything at
  least $0.01 in the money is exercised or assigned.
- **Interest:** all cash earns the T-bill rate. It accrues daily and is paid on the 15th (or the business day
  before, when the 15th isn't a trading day).
- **Account value:** cash + collateral + accrued interest + shares at market. What it would cost to buy back
  your open options is not counted.

## Calendar and alerts

- **Calendar:** Portfolio has a month calendar with your expiries, TQQQ's daily closes, market holidays,
  interest pay dates and the days you traded.
- **Market events:** Fed rate decisions, CPI and jobs-report days come from the official schedules built into
  `ghost_trader/events.py`. Update that file once a year when the Fed and BLS publish the next year.
- **Expiration-day alert:** a systemd user timer (`ghost-trader-nudge.timer`, weekdays 7:45 AM CT) runs
  `ghost-trader --notify` and sends a desktop notification on mornings your options expire. It needs
  `libnotify` and a notification daemon such as `mako`.

The full design lives in the project spec (`ghost-trader-spec.md` in the Claude project).

## Install (Arch Linux)

From the AUR, once the package is listed there:

```
yay -S ghost-trader
```

Until then, build it straight from this repo (yay pulls in the dependencies, including python-yfinance):

```
git clone https://github.com/flak-daddy/ghost-trader-source.git
cd ghost-trader-source/packaging/arch
yay -Bi .
```

## First launch

1. Open **Ghost Trader** from your app menu (or run `ghost-trader`). It refreshes its data, then asks how much paper
   cash to start with. You get your own paper account; nothing is shared with anyone.
2. **Free Alpha Vantage key (optional, recommended).** It supplies the 3-month Treasury rate that your cash earns.
   - Open https://www.alphavantage.co/support/#api-key
   - Fill in the short form (an email and a word about what it's for). The key appears right on the page;
     there's no confirmation email.
   - In Ghost Trader, open **Settings → Alpha Vantage API key**, paste it, and click outside the box to save.
     Settings also has a **Get a free key** link to that page.
   - The free tier allows about 25 requests a day; Ghost Trader uses one or two per launch. Without a key,
     the rate comes from Yahoo's ^IRX instead.
3. **Expiration-day notifications (optional).** On Hyprland or Sway: `sudo pacman -S libnotify mako`, then add
   `exec-once = mako` to your Hyprland config. Use **Settings → Send test** to check.
4. **Updates.** When a new version is out, Ghost Trader says so at startup. Run `yay -Syu` (AUR install), or
   `git pull` in `ghost-trader-source` and then `yay -Bi .` in `packaging/arch` (built from the repo).

## Install for development (Arch + Hyprland)

1. Install the packages for the native window:
   ```
   sudo pacman -S --needed webkit2gtk-4.1 python-gobject git openssh
   ```
2. Clone this repo to `~/Projects/ghost-trader` with the read-only deploy key.
3. Open the folder in Code OSS. In the integrated terminal, run `./install.sh`.
4. Run `ghost-trader --check` to confirm Yahoo, `^IRX`, your Alpha Vantage key, the window libraries and the
   bundled fonts all work.
5. Launch Ghost Trader from the app menu (or run `ghost-trader`). The first launch asks for your starting
   cash. Then put your Alpha Vantage key in Settings.

`ghost-trader --demo` runs on synthetic data in a separate ledger (`~/.local/share/ghost-trader-demo`), so you
can try things without touching your real run.

## How updates work

1. Every change goes through a pull request.
2. The **Tests** workflow runs on each PR. A PR that changes the app must also raise `__version__` in
   `ghost_trader/__init__.py`.
3. When the PR is merged, the **Release** workflow tags `vX.Y.Z`. The tag message is the change list.
4. At the next startup, Ghost Trader asks "Update to vX.Y.Z?" and shows that change list. If you say yes, it
   backs up the ledger, checks out the tag and restarts.
5. If the new version fails its self-check, the app goes back to the previous release and restores the
   backup. If the new version crashes before it can run the self-check, the launcher does the same.

## Development

- Code OSS **Run** panel: "Run Ghost Trader", "Run --check", "Run demo" and "Run tests".
- Tests: `.venv/bin/python -m pytest -q`. Lint: `.venv/bin/ruff check .`.

Layout:

```
ghost_trader/
  ledger.py      accounts, trade rules, expirations, interest, snapshots
  marketcal.py   NYSE holidays / early closes / pay dates
  market.py      Yahoo + demo providers, rates, quote cache
  startup.py     the startup refresh (steps, retries, issue dialogs)
  api.py         everything the UI calls
  server.py      local HTTP server (127.0.0.1, per-launch token)
  window.py      native window and fallbacks
  updater.py     tagged-release updates and rollback
  static/        the UI (index.html, app.js, app.css, bundled Inter fonts)
tests/           pytest suite (uses the synthetic demo provider, no network)
```

Fonts: Inter (SIL Open Font License, see `ghost_trader/static/fonts/OFL.txt`).
