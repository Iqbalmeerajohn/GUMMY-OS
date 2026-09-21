# Running GUMMY 24/7, and reaching it from your phone

Two separate problems that are easy to conflate:

1. **Always-on** — the four processes stay up across reboots and crashes.
2. **Reachable** — you can talk to it when you are not at the machine.

You can have the first without the second. Do them in that order.

---

## 1. Always-on (Windows)

GUMMY is four long-lived processes:

| Process | Port | Supervised by |
| --- | --- | --- |
| PostgreSQL + pgvector | 5432 | Docker (`restart: unless-stopped`) |
| Ollama | 11434 | Scheduled Task |
| Backend (API + workers + scheduler) | 8000 | Scheduled Task |
| Frontend | 3000 | Scheduled Task |

Postgres is deliberately left to Docker. It already restarts itself, and a
second supervisor would just race it to start the same container.

### Install

```powershell
cd E:\GUMMY-OS
powershell -ExecutionPolicy Bypass -File ops\windows\gummy-service.ps1 install
```

No administrator rights are needed, because nothing here is machine-wide. That
is also *why* these are Scheduled Tasks rather than Windows Services: a real
service runs in session 0 with no user profile, and Ollama's model cache, the
backend's `.venv` and `.env`, and your GPU access all live in your profile.

Then, once:

```powershell
cd E:\GUMMY-OS\frontend; npm run build
```

The task runs `npm run start`, which serves that build. Do not point it at
`npm run dev` — the dev server is slower, rebuilds constantly, and is not
meant to run for weeks.

Finally, in Docker Desktop → Settings → General, enable **Start Docker Desktop
when you log in**, so Postgres is up before the backend tries to reach it.

### Check it

```powershell
powershell -ExecutionPolicy Bypass -File ops\windows\gummy-service.ps1 status
```

Each service writes to `%LOCALAPPDATA%\GummyOS\logs\`. The wrapper scripts log
every restart with a timestamp, so a crash-loop is visible rather than silent.

### The part Windows will get wrong

**Sleep.** A scheduled task cannot run on a sleeping laptop. Nothing above
fixes that, and "always-on" is a lie until you do:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Leave the battery timeouts alone unless you want a flat battery. If the machine
is a laptop that travels, accept that GUMMY is up when the lid is open, or move
the always-on half to a machine that does not sleep.

### Resource reality on this hardware

16 GB RAM and a 4 GB GPU is enough, but not with room to spare:

| | Roughly |
| --- | --- |
| Postgres | 300–600 MB |
| Ollama + `qwen2.5:3b` resident | 2.5–3 GB |
| Backend | 400–700 MB |
| Frontend (built, not dev) | 150–250 MB |

Two things matter. Keep `OLLAMA_KEEP_ALIVE` long enough that the model is not
reloaded on every message, and do **not** switch the default to an 8B model:
`qwen2.5:3b` fits in 4 GB of VRAM, while an 8B model spills to CPU and runs
several times slower for every turn, forever.

---

## 2. Reaching it from your phone

Three options, best first.

### Telegram (recommended)

The only option that needs no inbound network exposure at all — the backend
polls Telegram outbound, so there is nothing to port-forward and nothing to
leave open.

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Put it in `backend/.env` as `GUMMY_TELEGRAM_BOT_TOKEN`.
3. Message your bot once, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the numeric
   `"chat":{"id":…}`.
4. Set `GUMMY_TELEGRAM_ALLOWED_CHAT_IDS` to that id, and
   `GUMMY_TELEGRAM_OWNER_USER_ID` to your GUMMY user id:
   ```sql
   SELECT id FROM users WHERE email = 'you@example.com';
   ```
5. Restart the backend. The log will say how many chats it is serving.

**The allowlist is enforced, not advisory.** The worker refuses to start
without one, because a bot token addresses a globally reachable endpoint —
anyone who learns the handle can message it.

What you give up: Telegram's servers relay the message text. Everything else —
the model, the memory, the database — stays on your machine. If that relay is
unacceptable for your data, use the tunnel below instead.

### Installable PWA over a tunnel

The full UI — files, goals, dashboards — on your home screen.

```bash
cloudflared tunnel --url http://localhost:3000
```

Open the printed `https://….trycloudflare.com` on your phone, then **Add to
Home Screen**. It installs as a standalone app: no browser chrome, its own
icon, and an offline page that tells you your phone cannot reach the machine
rather than showing a browser error.

Two things to get right:

- Set `BACKEND_CORS_ORIGINS` to the tunnel URL, or the browser will block every
  API call.
- A quick tunnel's URL changes on every restart. For something durable, use a
  named tunnel with your own domain.

**This one is genuinely exposed to the internet.** Anyone with the URL reaches
your login page, so it is only as strong as your password. Use a long one.

### Same Wi-Fi only

Bind the backend to `0.0.0.0`, reach it at `http://<your-lan-ip>:3000`. Nothing
leaves the house; nothing works when you do.

---

## Verifying it actually survives

Not "it started", but "it comes back":

```powershell
# 1. Kill the backend. The wrapper should restart it within ~10s.
Stop-Process -Name python -Force
Start-Sleep 20
powershell -ExecutionPolicy Bypass -File ops\windows\gummy-service.ps1 status

# 2. Reboot, log in, wait a minute, then check again — without starting
#    anything by hand.
```

If step 2 needs manual intervention, it is not always-on yet. The usual cause
is Docker Desktop not being set to start at login, which leaves the backend
restarting in a loop against a database that is not there — visible in
`%LOCALAPPDATA%\GummyOS\logs\GummyOS-Backend.log`.
