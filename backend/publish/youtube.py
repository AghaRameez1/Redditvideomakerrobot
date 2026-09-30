"""Upload to YouTube with the YouTube Data API v3.

Needs OAuth (an API key can't upload). Uses the same Google OAuth client as "Sign in with
Google", with the YouTube Data API enabled on that Google Cloud project.

Google restricts uploads from unaudited projects: "All videos uploaded via the videos.insert
endpoint from unverified API projects created after 28 July 2020 will be restricted to private
viewing mode." Uploads also cost quota, with a default of 100 uploads a day.
"""
import json

import google.auth.exceptions
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import PublishError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]  # readonly: to show the channel name
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
PRIVACY = ("private", "unlisted", "public")
PEOPLE_AND_BLOGS = "22"


def _service(creds):
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _reasons(exc: HttpError) -> set:
    """Google's machine-readable reasons, e.g. {"accessNotConfigured", "SERVICE_DISABLED"}."""
    try:
        err = json.loads(exc.content.decode()).get("error", {})
    except (ValueError, AttributeError):
        return set()
    return {d.get("reason") for d in (err.get("errors") or []) + (err.get("details") or []) if isinstance(d, dict)}


def _error(exc, doing="upload the video"):
    if isinstance(exc, google.auth.exceptions.RefreshError):
        return PublishError("YouTube access was revoked or has expired. Reconnect YouTube in Settings.")
    if isinstance(exc, HttpError):
        reasons, status, message = _reasons(exc), exc.resp.status, str(exc.reason or "")
        if reasons & {"accessNotConfigured", "SERVICE_DISABLED"}:
            return PublishError("The YouTube Data API v3 isn't turned on for this app's Google Cloud project. The site "
                                "owner needs to enable it (APIs & Services, Library), wait a few minutes, then "
                                "connect again.")
        if reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
            return PublishError("Google didn't grant every permission this needs. Connect YouTube again and tick "
                                "all the boxes Google shows.")
        if "youtubeSignupRequired" in reasons:
            return PublishError("That Google account has no YouTube channel yet. Create one on YouTube first.")
        if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
            return PublishError("YouTube's daily limit for this app has been reached. Try again tomorrow.")
        if "uploadLimitExceeded" in reasons:
            return PublishError("This YouTube channel has reached its own upload limit for now. Try again later.")
        if status == 401:
            return PublishError("YouTube access has expired. Reconnect YouTube in Settings.")
        # Anything else: show Google's own explanation rather than guessing.
        return PublishError(f"YouTube wouldn't let this app {doing} ({status}): {message}")
    return PublishError(f"YouTube failed: {exc}")


def channel(access_token: str) -> dict:
    """The signed-in user's channel: {"id", "name"}."""
    try:
        resp = _service(Credentials(token=access_token)).channels().list(part="snippet", mine=True).execute()
    except (HttpError, google.auth.exceptions.GoogleAuthError) as exc:
        raise _error(exc, "read your channel")
    items = resp.get("items") or []
    if not items:
        raise PublishError("That Google account has no YouTube channel yet. Create one on YouTube first.")
    return {"id": items[0]["id"], "name": items[0]["snippet"]["title"]}


def upload(refresh_token, client_id, client_secret, path, title, description, privacy, on_progress) -> str:
    """Upload the video and return its YouTube Shorts link. on_progress gets 0-100."""
    creds = Credentials(token=None, refresh_token=refresh_token, token_uri=TOKEN_URI,
                        client_id=client_id, client_secret=client_secret, scopes=SCOPES)
    body = {
        "snippet": {"title": title[:100], "description": description[:5000], "categoryId": PEOPLE_AND_BLOGS},
        "status": {"privacyStatus": privacy if privacy in PRIVACY else "private",
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
    try:
        request = _service(creds).videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                on_progress(int(status.progress() * 100))
    except (HttpError, google.auth.exceptions.GoogleAuthError) as exc:
        raise _error(exc)
    return f"https://youtube.com/shorts/{response['id']}"
