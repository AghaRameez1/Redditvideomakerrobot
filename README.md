# Script Studio

Turn a script into a vertical 1080×1920 video for YouTube Shorts, Instagram Reels or TikTok:
a voiceover, one styled text card per sentence, and gameplay footage behind it. People sign up,
write a script themselves or have AI draft it with their own Claude, ChatGPT or Gemini key,
and render.

Based on [RedditVideoMakerBot](https://github.com/elebumm/RedditVideoMakerBot) by elebumm,
rewritten to work from your own scripts instead of Reddit threads. GPL-3.0, see `LICENSE`.

## Setup

Needs Python 3.11 or newer (3.12 recommended) and ffmpeg.

```bash
brew install ffmpeg
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5050 and create an account. On first start the app generates its secrets
and database in `instance/` (never commit that folder).

Then make your account an admin (run it in the project folder, with the venv active):

```bash
flask --app app make-admin you@example.com          # add --remove to take it away
```

An **Admin** link then appears in the top bar. From there you can add, edit and remove users and
give them roles, so you only need this command once. (`--role manager` gives the manager role;
`--remove` makes someone a plain user.)

## Features

- **Home page:** visitors who aren't signed in see a page explaining what the app does, with
  **Sign up** and **Sign in** buttons. Signed-in people go straight to the Studio.
- **Accounts:** email and password, or Google (see below). Each user sees only their own videos.
- **AI script writer:** in **Settings**, users add a key for Claude, ChatGPT and/or Gemini and pick
  a model. Keys are checked before saving (free), encrypted in the database, and never sent back
  to the browser. The AI company bills the user's own account. The server never uses its own key.
- **Studio:** voice, background, music, and the card look, with a live preview and progress bar.
  Renders run on the server, so refreshing or closing the page doesn't stop them: the Studio picks
  the progress back up, and My videos shows a "rendering" card until the video is ready.
- **Your own footage:** upload background clips (MP4, MOV, WebM or MKV, up to 500 MB each, 20 clips
  and 3 GB per person) after confirming you have the rights. Any shape works; it's cropped to 9:16
  from the centre. Using your own footage avoids relying on other creators' gameplay.
- **Word-by-word captions:** the "Word by word" caption mode (or the **Word pop** preset) shows 1-5
  words at a time and highlights each word as it's spoken. The voices don't report word timings, so
  timing is estimated from word length: close, not exact.
- **Scheduled posts:** in the YouTube share dialog, pick **Schedule** and a time (15 minutes to 6
  months ahead). The video uploads straight away as private, and YouTube publishes it at that time
  itself, even if this app is off.
- **My videos:** a stats strip (videos made, total length, how many are posted to YouTube, space
  used), then every finished video, with a thumbnail, playback, download, delete, and
  **Share to YouTube** with a live upload status and a link to the post. The
  suggested description includes the footage credit.
  **Delete** removes a video completely. For a posted video it can instead remove only the file
  from this computer and keep the entry, its thumbnail and its YouTube link.
- **Connected accounts:** in **Settings**, users connect YouTube once by signing in with Google
  (OAuth). An API key can't be used to post. Tokens are encrypted like AI keys.
- **Plans:** Free (3 videos a month, with a small "Made with Script Studio" label), Creator ($9, 60
  videos) and Pro ($24, 300 videos); yearly is 10 months. The limit counts renders since the 1st
  (UTC), so deleting a video doesn't free a slot. Staff have no limit. There's **no payment provider
  yet**: users pick a plan in **Settings → Plan & billing**, and an admin or manager approves it under
  **Admin → Upgrade requests** after being paid. Admins can change prices and limits in **Admin**.
  **Admin → Payments** (admins) stores the payment service settings for later: service, test or live
  mode, store ID, API key and webhook secret (encrypted), checkout links, and the webhook address.
  Saving them doesn't switch on card payments yet; that's built once the app is public.
- **Works on phones:** every page fits a phone screen, with a Menu button for the top bar.
- **Roles:** **User** makes videos. **Manager** also sees the admin page and can add, edit and
  remove users. **Admin** can do everything, including giving roles and changing site settings.
  Nobody can change their own role, and the last admin can't be removed or demoted.
- **Admin page** (`/admin`, admins and managers):
  - **Overview:** users, sign-ups and active users this week, sign-in methods, AI keys, videos,
    YouTube posts, disk use, and 30-day charts of sign-ups and videos.
  - **Users:** everyone's numbers, a filter, and **Add user**, **Edit** (name, email, role, new
    password) and **Delete**.
  - **Auto-clean** (admins): removes posted videos' files from this computer after a delay you pick.
    Off by default; the entry and its YouTube link stay. For cron on a server:
    `flask --app app cleanup`.
  - **Google client ID and secret** (admins): for Google sign-in and YouTube. Checked with Google
    before saving, encrypted, and applied without a restart.
- **Command line** (no accounts): `python make_video.py example_script.txt`
  (options: `--voice google:co.uk --background gta --music none --style style.json`).

## Sign in with Google (optional)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project, then
   **APIs & Services → OAuth consent screen**: choose **External**, and fill in the app name and
   your email.
2. **Credentials → Create credentials → OAuth client ID → Web application.** Add this under
   *Authorised redirect URIs*: `http://127.0.0.1:5050/auth/google/callback` (and later
   `https://your-domain/auth/google/callback`).
3. Open **Admin**, paste the client ID and secret, and click **Check and save**. The page also lists
   the exact redirect URIs to add, with Copy buttons. The **Continue with Google** button appears
   straight away.

   On a server you can use environment variables instead (`GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`). When set, they take priority and the admin page only displays them.

If someone signs up with email and password and a person later signs in with Google using the
same address, the verified Google owner gets the account and the password is removed. That
stops anyone from pre-registering someone else's email.

## Sharing to YouTube (optional)

Uses the same Google OAuth client as sign-in.

1. In the same Google Cloud project: **APIs & Services → Library → YouTube Data API v3 → Enable.**
2. **OAuth consent screen → Scopes:** add `.../auth/youtube.upload` and `.../auth/youtube.readonly`.
   While the app is in *Testing*, add your own Google account under **Test users**.
3. **Credentials → your OAuth client:** also add the redirect URI
   `http://127.0.0.1:5050/connect/youtube/callback`.
4. With the client saved on the admin page, use **Settings → Connect YouTube**.

Switching to a different client ID removes existing YouTube connections, because Google ties each
connection to the client that made it. Those users connect again.

Google's rules to know about:
- **Uploads are private until your project passes Google's audit.** Google: "All videos uploaded
  via the videos.insert endpoint from unverified API projects created after 28 July 2020 will be
  restricted to private viewing mode." Change visibility afterwards in YouTube Studio, or apply
  for the audit (the YouTube API Services audit and quota extension form).
- Default quota is **100 uploads a day** for the whole app, shared by all users.

## Looking at the database

It's a single SQLite file: `instance/app.db`.

```bash
sqlite3 -header -column instance/app.db
.tables
SELECT id, email, name, is_admin, created_at FROM users;
SELECT user_id, provider, hint, model FROM api_keys;
.quit
```

GUI options: [DB Browser for SQLite](https://sqlitebrowser.org) (free), TablePlus, or the
*SQLite Viewer* extension in VS Code. Open `instance/app.db`.

Tables: `users`, `api_keys` (AI keys), `videos` (My videos), `connections` (YouTube channels),
`shares` (every post attempt, with its link or error), `site_settings` (admin page values, encrypted).

What you'll see: passwords are scrypt hashes, and `api_keys.key_enc` / `connections.token_enc` are
encrypted, so none of them can be read back. That's deliberate. Avoid editing rows while the app is running, and copy the file
before any manual change.

## Deploying with Docker

`docker-compose.yml` runs the app (gunicorn, one worker) behind **Caddy**, which gets and renews a
free HTTPS certificate automatically. Use a server with at least 2 CPU cores and 4 GB of RAM.

1. Point your domain's DNS (an `A` record) at the server, and open ports 80 and 443.
2. Install Docker, copy the project to the server, then create the settings file:
   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"                                # SECRET_KEY
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # ENCRYPTION_KEY
   ```
   Put your domain and the two keys in `.env`. **Keep a copy of `ENCRYPTION_KEY` somewhere safe.**
3. Start it, then make yourself an admin after signing up on the site:
   ```bash
   docker compose up -d --build
   docker compose exec app flask --app wsgi make-admin you@example.com
   ```
4. Add the https redirect URIs shown on the Admin page to Google Cloud.

Everyday commands: `docker compose logs -f app` (logs), `git pull && docker compose up -d --build`
(update), `docker compose down` (stop; data is kept).

**Where data lives:** the `data` volume holds the database and users' videos, so **back it up**, for
example with `docker run --rm -v scriptstudio_data:/data -v "$PWD":/backup busybox tar czf
/backup/data.tgz /data`. The
`backgrounds` volume caches downloaded gameplay and can be re-downloaded.

To try it on your own computer first, set `DOMAIN=localhost` and open https://localhost (your
browser warns about the local certificate).

## Going live

The app runs as a normal website, but several things must change for the internet:

- Set `APP_ENV=production` plus `SECRET_KEY`, `ENCRYPTION_KEY` (generate with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`),
  and the Google variables if you use them. Production refuses to start without the secrets. **Back up
  `ENCRYPTION_KEY`:** if you lose it, every saved AI key and account connection becomes unreadable.
- Add your https redirect URIs in Google Cloud, and complete Google's YouTube audit so uploads
  can be public.
- Serve it over **HTTPS** behind a reverse proxy with `TRUST_PROXY=1`, using gunicorn with **one**
  worker (`wsgi.py`), not `python app.py`. The Docker setup above does all of this.
- Renders use a lot of CPU and run one at a time, so a busy site needs a bigger server or a
  job queue. Videos are stored on local disk (`RESULTS_DIR`), so plan disk space, or move them
  to object storage.
- Still to build before real users: email verification and password reset (these need an email
  service).

## Project layout

```
app.py              start the web app
wsgi.py             production entry point (gunicorn), used by the Docker image
Dockerfile, docker-compose.yml, Caddyfile, .env.example   Docker deployment with HTTPS
make_video.py       command-line entry point (no accounts)
frontend/           HTML, CSS and JS only; talks to the backend over JSON
  landing.html        public home page (signed-out visitors)
  login.html          sign in / create account
  index.html          the studio (dashboard)
  library.html        My videos: play, download, share
  settings.html       AI keys, connected accounts, account
  admin.html          admins and managers: overview, requests, users, plans, auto-clean, Google
backend/            Flask app
  auth.py             sign-up, sign-in, Google, sign out, delete account
  api.py              studio + AI-key API, all scoped to the signed-in user
  footage.py          users' own background clips: upload, list, delete
  library.py          My videos + share endpoints
  connections.py      Connect / disconnect YouTube (OAuth)
  admin.py            admin page API: stats, users and roles, auto-clean, Google client
  billing.py          public plans, each user's plan and usage, upgrade requests
  plans.py            plan prices, monthly limits and the free-plan watermark
  cleanup.py          auto-clean of posted videos (background check + `flask cleanup`)
  site_settings.py    settings saved from the admin page, encrypted
  publish/            youtube.py (Data API upload)
  shares.py           background uploads with progress
  security.py         sessions, roles, cross-site protection, encryption, login throttling
  db.py / config.py   SQLite schema, secrets and settings
  jobs.py             background renders
engine/             the video maker, usable without the web app
  ai/                 script writing: prompt.py + one file per provider
  pipeline.py         make_video(): the steps below, in order
  script.py tts.py cards.py backgrounds.py render.py catalog.py
instance/           secrets + database (created on first run, not in git)
results/user-N/     each user's videos (not in git)
```

## Things to know

- **Credit the footage.** Backgrounds are other creators' gameplay (credits are in
  `engine/data/background_videos.json`). For commercial use, get permission or use your own footage.
- **First use of a background downloads it** from YouTube: a few GB, once.
- **Render speed depends on the footage codec.** Downloads prefer H.264. The Minecraft
  background downloaded earlier is AV1, which Macs before the M3 decode slowly. Delete
  `assets/backgrounds/video/bbswitzer-parkour.mp4` to re-download it as H.264.
