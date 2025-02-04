import json
import re
from pathlib import Path
from typing import Dict, Final

import translators
from playwright.sync_api import ViewportSize, sync_playwright
from rich.progress import track

from utils import settings
from utils.console import print_step, print_substep
from utils.imagenarator import imagemaker
from utils.playwright import clear_cookie_by_name
from utils.videos import save_data

__all__ = ["get_screenshots_of_reddit_posts", "get_screenshots_of_reddit_posts_comments"]


def get_screenshots_of_reddit_posts(reddit_object: dict, screenshot_num: int):
    """Downloads screenshots of reddit posts as seen on the web. Downloads to assets/temp/png

    Args:
        reddit_object (Dict): Reddit object received from reddit/subreddit.py
        screenshot_num (int): Number of screenshots to download
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    lang: Final[str] = settings.config["reddit"]["thread"]["post_lang"]
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    print_step("Downloading screenshots of reddit posts...")
    reddit_id = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
    # ! Make sure the reddit screenshots folder exists
    Path(f"assets/temp/{reddit_id}/png").mkdir(parents=True, exist_ok=True)

    # set the theme and disable non-essential cookies
    if settings.config["settings"]["theme"] == "dark":
        cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
        transparent = False
    elif settings.config["settings"]["theme"] == "transparent":
        if storymode:
            # Transparent theme
            bgcolor = (0, 0, 0, 0)
            txtcolor = (255, 255, 255)
            transparent = True
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        else:
            # Switch to dark theme
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
            bgcolor = (33, 33, 36, 255)
            txtcolor = (240, 240, 240)
            transparent = False
    else:
        cookie_file = open("./video_creation/data/cookie-light-mode.json", encoding="utf-8")
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)
        transparent = False

    if storymode and settings.config["settings"]["storymodemethod"] == 1:
        # for idx,item in enumerate(reddit_object["thread_post"]):
        print_substep("Generating images...")
        return imagemaker(
            theme=bgcolor,
            reddit_obj=reddit_object,
            txtclr=txtcolor,
            transparent=transparent,
        )

    screenshot_num: int
    with sync_playwright() as p:
        print_substep("Launching Headless Browser...")

        browser = p.chromium.launch(
            headless=True
        )  # headless=False will show the browser for debugging purposes
        # Device scale factor (or dsf for short) allows us to increase the resolution of the screenshots
        # When the dsf is 1, the width of the screenshot is 600 pixels
        # so we need a dsf such that the width of the screenshot is greater than the final resolution of the video
        dsf = (W // 600) + 1

        context = browser.new_context(
            locale=lang or "en-us",
            color_scheme="dark",
            viewport=ViewportSize(width=W, height=H),
            device_scale_factor=dsf,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        )
        cookies = json.load(cookie_file)
        cookie_file.close()

        context.add_cookies(cookies)  # load preference cookies

        # Login to Reddit
        print_substep("Logging in to Reddit...")
        page = context.new_page()
        page.goto("https://www.reddit.com/login", timeout=0)
        page.set_viewport_size(ViewportSize(width=1920, height=1080))
        page.wait_for_load_state()

        page.locator(f'input[name="username"]').fill(settings.config["reddit"]["creds"]["username"])
        page.locator(f'input[name="password"]').fill(settings.config["reddit"]["creds"]["password"])
        page.get_by_role("button", name="Log In").click()
        page.wait_for_timeout(5000)
        page.wait_for_load_state()
        # Get the thread screenshot
        page.goto(reddit_object["thread_url"], timeout=0, wait_until='domcontentloaded')
        page.set_viewport_size(ViewportSize(width=W, height=H))
        page.wait_for_load_state()
        page.wait_for_timeout(5000)
        page.wait_for_load_state()  # Wait for page to fully load

        postcontentpath = f"assets/temp/{reddit_id}/png/title.png"
        id = f"#t3_{reddit_id}"
        try:
            if settings.config["settings"]["zoom"] != 1:
                # store zoom settings
                zoom = settings.config["settings"]["zoom"]
                # zoom the body of the page
                page.evaluate("document.body.style.zoom=" + str(zoom))
                # as zooming the body doesn't change the properties of the divs, we need to adjust for the zoom
                location = page.locator(id).bounding_box()
                for i in location:
                    location[i] = float("{:.2f}".format(location[i]))
                page.screenshot(clip=location, path=postcontentpath)
            else:
                pass
                page.locator(id).screenshot(path=postcontentpath)
        except Exception as e:
            print_substep("Something went wrong!", style="red")
            resp = input(
                "Something went wrong with making the screenshots! Do you want to skip the post? (y/n) "
            )

            if resp.casefold().startswith("y"):
                save_data("", "", "skipped", reddit_id, "")
                print_substep(
                    "The post is successfully skipped! You can now restart the program and this post will skipped.",
                    "green",
                )

            resp = input("Do you want the error traceback for debugging purposes? (y/n)")
            if not resp.casefold().startswith("y"):
                exit()

            raise e
        print_substep("Screenshots downloaded Successfully.", style="bold green")
        print_substep("Launching Headless Browser for comments...")
        for idx, comment in enumerate(
            track(
                reddit_object["comments"][:screenshot_num],
                "Downloading screenshots...",
            )
        ):
            # Stop if we have reached the screenshot_num
            if idx >= screenshot_num:
                break

            page.goto(f"https://new.reddit.com/{comment['comment_url']}", wait_until='domcontentloaded')
            try:
                commentid=f"[thingid=t1_{comment['comment_id']}][depth='0']"
                if settings.config["settings"]["zoom"] != 1:
                # store zoom settings
                    zoom = settings.config["settings"]["zoom"]
                # zoom the body of the page
                    page.evaluate("document.body.style.zoom=" + str(zoom))
                # as zooming the body doesn't change the properties of the divs, we need to adjust for the zoom
                    location = page.locator('#comment-children').first.evaluate("element => element.style.display = 'none'")
                    location = page.locator(commentid).bounding_box()
                # post_colided = input("Post Colided: ?")
                # if post_colided == 'y' or post_colided == "Y" and settings.config["settings"]["zoom"] != 1:
                #     location = page.locator(commentid).bounding_box()
                #     for i in location:
                #         location[i] = float("{:.2f}".format(location[i]))
                #     page.screenshot(clip=location,path=f"assets/temp/{reddit_id}/png/comment_{idx}.png")
                # else:
                    page.locator(commentid).screenshot(path=f"assets/temp/{reddit_id}/png/comment_{idx}.png")
            except TimeoutError:
                del reddit_object["comments"]
                screenshot_num += 1
                print("TimeoutError: Skipping screenshot...")
                continue

        # close browser instance when we are done using it
        browser.close()

        print_substep("Screenshots downloaded Successfully.", style="bold green")
