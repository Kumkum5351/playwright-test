
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import csv
import html
import re
import base64

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

URL = "https://ikarkhana-dev.web.app/"

ARTIFACTS = Path("artifacts").resolve()
VIDEOS = ARTIFACTS / "videos"

ARTIFACTS.mkdir(parents=True, exist_ok=True)
VIDEOS.mkdir(parents=True, exist_ok=True)

ACCOUNTS = [
    {
        "email": "karanbhatia@yopmail.com",
        "password": "kumkum@123",
        "expected": "valid",
    },
    {
        "email": "sajal@yopmail.com",
        "password": "Indixpert@123",
        "expected": "valid",
    },
    {
        "email": "ananyaverma02@yopmail.com",
        "password": "kumkum@123",
        "expected": "valid",
    },
]

ERROR_PATTERN = re.compile(
    r"invalid credentials|invalid email or password|"
    r"incorrect password|login failed|invalid password|"
    r"unable to login|something went wrong",
    re.IGNORECASE,
)


def run_test(account):
    email = account["email"]
    expected = account["expected"]
    safe_name = email.split("@")[0]

    result = {
        "email": email,
        "expected": expected,
        "status": "FAIL",
        "details": "",
        "url": "",
        "screenshot": "",
        "video": "",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )

        context = browser.new_context(
            viewport=None,
            record_video_dir=str(VIDEOS),
            record_video_size={"width": 1365, "height": 768},
        )

        page = context.new_page()

        try:
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.get_by_placeholder("Enter your email").fill(email)
            page.get_by_placeholder("Enter your password").fill(
                account["password"]
            )

            before_path = ARTIFACTS / f"{safe_name}_before.png"
            page.screenshot(
                path=str(before_path),
                full_page=True,
            )

            page.get_by_role("button", name="Sign In").click()
            page.wait_for_timeout(5000)

            current_url = page.url
            result["url"] = current_url

            error_visible = False

            try:
                page.get_by_text(ERROR_PATTERN).first.wait_for(
                    state="visible",
                    timeout=2000,
                )
                error_visible = True
            except PlaywrightTimeoutError:
                pass

            still_on_signin = (
                "/auth/signin" in current_url.lower()
                or current_url.lower().rstrip("/").endswith("/signin")
            )

            authenticated = False

            if not still_on_signin:
                selectors = [
                    page.get_by_role(
                        "button",
                        name=re.compile(
                            r"log out|logout|sign out",
                            re.IGNORECASE,
                        ),
                    ),
                    page.get_by_text(
                        re.compile(
                            r"dashboard|my account",
                            re.IGNORECASE,
                        )
                    ),
                ]

                for locator in selectors:
                    try:
                        locator.first.wait_for(
                            state="visible",
                            timeout=1500,
                        )
                        authenticated = True
                        break
                    except PlaywrightTimeoutError:
                        continue

            if expected == "invalid":
                if error_visible and still_on_signin:
                    result["status"] = "PASS"
                    result["details"] = (
                        "Wrong password correctly rejected."
                    )
                elif authenticated:
                    result["details"] = (
                        "Authenticated screen appeared for the "
                        "intentionally incorrect-password test."
                    )
                else:
                    result["details"] = (
                        "Login rejection not confirmed. Check the "
                        "website's actual error message."
                    )

            else:
                if authenticated:
                    result["status"] = "PASS"
                    result["details"] = (
                        "Authenticated screen detected after login."
                    )
                elif error_visible:
                    result["details"] = (
                        "Login error appeared for an account expected "
                        "to be valid."
                    )
                else:
                    result["details"] = (
                        "Login success not confirmed. The dashboard "
                        "selector may need updating."
                    )

            result["url"] = page.url

            after_path = ARTIFACTS / f"{safe_name}_after.png"
            page.screenshot(
                path=str(after_path),
                full_page=True,
            )
            result["screenshot"] = str(after_path.resolve())

        except Exception as error:
            result["details"] = f"Test error: {error}"
            result["url"] = page.url

            try:
                failure_path = ARTIFACTS / f"{safe_name}_failure.png"
                page.screenshot(
                    path=str(failure_path),
                    full_page=True,
                )
                result["screenshot"] = str(failure_path.resolve())
            except Exception:
                pass

        finally:
            video = page.video

            # Closing context finalizes the video recording.
            context.close()

            if video:
                video_path = Path(video.path())

                if video_path.is_file():
                    # Copy the finalized video to a stable account-specific name.
                    stable_video = VIDEOS / f"{safe_name}.webm"

                    if video_path.resolve() != stable_video.resolve():
                        import shutil
                        shutil.copy2(video_path, stable_video)

                    result["video"] = str(stable_video.resolve())

            browser.close()

    print(
        f"{result['status']} | {email} | {result['details']}"
    )
    return result


def generate_html_report(results):
    report_path = ARTIFACTS / "report.html"

    total = len(results)
    passed = sum(r["status"] == "PASS" for r in results)
    failed = sum(r["status"] == "FAIL" for r in results)

    rows = []

    for result in results:
        status = result["status"]
        css_class = "pass" if status == "PASS" else "fail"

        screenshot_path = (
            Path(result["screenshot"])
            if result["screenshot"]
            else None
        )

        video_path = (
            Path(result["video"])
            if result["video"]
            else None
        )

        if screenshot_path and screenshot_path.is_file():
            screenshot_link = (
                f'<a href="{html.escape(screenshot_path.name)}" '
                'target="_blank">View screenshot</a>'
            )
        else:
            screenshot_link = "Not available"

        # Embed the video in the HTML file itself.
        if video_path and video_path.is_file():
            video_data = base64.b64encode(
                video_path.read_bytes()
            ).decode("ascii")

            video_link = (
                '<video width="280" controls preload="metadata">'
                f'<source src="data:video/webm;base64,{video_data}" '
                'type="video/webm">'
                'Your browser does not support this video.'
                '</video>'
            )
        else:
            video_link = "Video file not found"

        rows.append(
            f"""
            <tr>
                <td>{html.escape(result['email'])}</td>
                <td>{html.escape(result['expected'])}</td>
                <td class="{css_class}">{html.escape(status)}</td>
                <td>{html.escape(result['details'])}</td>
                <td class="url">{html.escape(result['url'])}</td>
                <td>{screenshot_link}</td>
                <td>{video_link}</td>
            </tr>
            """
        )

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Automated Login Test Report</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 28px;
    background: #f4f6f9;
    color: #222;
}}
h1 {{ color: #25354a; }}
.summary {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin: 20px 0;
}}
.card {{
    background: white;
    padding: 18px 24px;
    border-radius: 8px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    background: white;
}}
th, td {{
    padding: 12px;
    border: 1px solid #ddd;
    text-align: left;
    overflow-wrap: anywhere;
    vertical-align: top;
}}
th {{ background: #25354a; color: white; }}
.pass {{ color: #16803c; font-weight: bold; }}
.fail {{ color: #c62828; font-weight: bold; }}
a {{ color: #1769aa; }}
.url {{ min-width: 180px; }}
video {{ max-width: 280px; }}
</style>
</head>
<body>
<h1>Automated Login Test Report</h1>
<p>Generated automatically after each test run.</p>

<div class="summary">
    <div class="card">Total tests: <strong>{total}</strong></div>
    <div class="card">PASS: <strong class="pass">{passed}</strong></div>
    <div class="card">FAIL: <strong class="fail">{failed}</strong></div>
</div>

<table>
<thead>
<tr>
    <th>Email</th>
    <th>Expected</th>
    <th>Status</th>
    <th>Details</th>
    <th>URL</th>
    <th>Screenshot</th>
    <th>Video recording</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""

    report_path.write_text(report_html, encoding="utf-8")
    print("HTML report:", report_path)


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(run_test, ACCOUNTS))

    csv_path = ARTIFACTS / "results.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "email",
                "expected",
                "status",
                "details",
                "url",
                "screenshot",
                "video",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    generate_html_report(results)

    print("\n========== TEST SUMMARY ==========")
    print("Total:", len(results))
    print("PASS:", sum(r["status"] == "PASS" for r in results))
    print("FAIL:", sum(r["status"] == "FAIL" for r in results))
    print("Report:", ARTIFACTS / "report.html")
    print("Screenshots:", ARTIFACTS)
    print("Videos:", VIDEOS)
