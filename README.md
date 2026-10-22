# waytime

Per-app and per-website screen time tracking for KDE Plasma (Wayland), with a CLI viewer.

This is [Loss-of-time's fork](https://github.com/Loss-of-time/waytime) of
[ieatfood314/waytime](https://github.com/ieatfood314/waytime). It adds **per-app
daily limits** on top of the upstream tracker: warn before an app runs out,
then close its windows (or kill its processes) and keep it blocked until
midnight. Upstream only tracks.

## How it works

- `waytime-daemon` runs as a systemd user service. It injects a small KWin
  script (via the `org.kde.kwin.Scripting` D-Bus interface) that reports every
  window activation and title change back to the daemon. Every 5 seconds the
  daemon credits elapsed time to the focused app in a SQLite database at
  `~/.local/share/waytime/waytime.db`.
- For browser windows (Zen, Firefox, Chromium, etc.) the daemon also parses the
  site name out of the window title (e.g. "Video - YouTube — Zen Browser" →
  "YouTube") and keeps a per-website table. It's a heuristic, not a URL —
  pages whose titles omit the site name get odd labels.
- Tracking pauses while the screen is locked, and suspend gaps are not counted.
- If KWin restarts, the daemon re-injects the tracker script automatically.
- History is kept forever (the DB grows by a few KB per day).

Requires KDE Plasma 6 — the daemon talks to KWin's scripting interface, so
other compositors and desktops (Hyprland, Sway, GNOME) would need their own
tracking backend. Built for Wayland; a Plasma 6 X11 session should also work
unchanged (same KWin D-Bus API), though that's untested.

## Install

This fork is not packaged on the AUR yet — the AUR `waytime` package is
upstream and has no limits. Install this clone per user (no root needed):

```
git clone https://github.com/Loss-of-time/waytime.git
cd waytime
mkdir -p ~/.local/bin ~/.config/systemd/user
install -m755 waytime waytime-daemon ~/.local/bin/
install -m644 waytime_core.py ~/.local/bin/
sed "s|/usr/bin/waytime-daemon|$HOME/.local/bin/waytime-daemon|" waytime.service > ~/.config/systemd/user/waytime.service
systemctl --user daemon-reload
systemctl --user enable --now waytime
```

### Other distros (Kubuntu, Fedora KDE, openSUSE, …)

Any distro running KDE Plasma 6 on Wayland works. You need python-gobject
(usually already present on KDE):

```
sudo apt install python3-gi        # Debian/Ubuntu/Kubuntu
sudo dnf install python3-gobject   # Fedora
sudo zypper install python3-gobject   # openSUSE
```

Then run the same install commands as above.

Make sure `~/.local/bin` is on your `PATH`. To uninstall:
`systemctl --user disable --now waytime`, then delete the installed files
(`waytime`, `waytime-daemon`, `waytime_core.py`) and the user unit.

## Usage

```
waytime                today's total and per-app breakdown
waytime yesterday      same, for yesterday
waytime week           per-day totals for the last 7 days
waytime history [N]    per-day totals for the last N days (default 14)
waytime apps [N]       per-app totals over the last N days (default 7)
waytime classes [N]    raw resourceClass values, e.g. for setting limits
waytime sites [N]      per-website totals over the last N days (default: today)
waytime 2026-07-01     breakdown for a specific date
waytime limits         configured limits and today's usage
waytime limit set APP MINUTES [--warn 15,5,1] [--action close|kill]
waytime limit clear APP
waytime events         today's limit warnings and enforcements
```

## Per-app daily limits

Limits are daily allowances for applications, counted the same way as the
tracker: **only while the app's window is focused** (locked screen and suspend
gaps do not count). Each limit is identified by the KWin `resourceClass`; use
`waytime classes 7` to see the raw values.

```sh
waytime limit set steam 90 --warn 15,5,1 --action close
waytime limit set discord 45 --warn 10 --action kill
waytime limits
```

This writes `~/.config/waytime/config.toml`:

```toml
[[limits]]
app = "steam"
minutes = 90
warn_minutes = [15, 5, 1]
action = "close"
```

| Field | Meaning |
|---|---|
| `app` | KWin `resourceClass`, case-insensitive (`steam`, `org.kde.dolphin`, …) |
| `minutes` | Daily allowance, reset at midnight |
| `warn_minutes` | Notify when this many minutes remain (thresholds ≥ `minutes` are ignored) |
| `action` | `close` asks the window to close; `kill` sends SIGTERM, then SIGKILL after 3 s |

Behaviour:

- Warnings are desktop notifications. They use critical urgency so they also
  appear above fullscreen games (Plasma suppresses normal notifications there)
  and are closed automatically after 10 s.
- When the allowance is used up the app's windows are closed and a
  "daily limit reached" notification is shown once. Reactivating the app
  closes it again; it stays blocked until the daily reset.
- The daemon re-reads the config when the file changes (within ~5 s), so
  limits can be added or removed while it runs.
- If the config is missing or malformed, limits are disabled and tracking
  continues.

## Service management

```
systemctl --user status waytime     # check the daemon
journalctl --user -u waytime -f     # follow its logs
systemctl --user restart waytime    # restart after an update
```

## Disclaimer

🤖 This project was vibe coded with Claude (Fable 5) — a human chose what to
build and verified it works; the AI wrote the code. Read it before you run it,
as you should with any stranger's daemon.
