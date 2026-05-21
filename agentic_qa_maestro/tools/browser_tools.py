"""
Playwright browser automation tools for Agentic QA Maestro agents.

Provides tools for browser-based UI testing: navigation, clicking,
filling forms, screenshots, page content extraction, and AAD authentication.
Uses a single dedicated thread for Playwright's sync API.
"""

import json
import os
import ssl
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Optional

from agent_framework import tool
from pydantic import Field

# --- Module-level browser state (singleton) ---
_playwright = None
_browser = None
_page = None
_pw_thread = ThreadPoolExecutor(max_workers=1)

_ACTION_TIMEOUT_MS = 15_000
_NAVIGATION_TIMEOUT_MS = 60_000


def _run_in_pw_thread(fn, *args, **kwargs):
    """Run a function in the dedicated Playwright thread."""
    future = _pw_thread.submit(fn, *args, **kwargs)
    return future.result(timeout=120)


def _do_start_browser(headless: bool):
    """Internal: launch Chromium in the PW thread."""
    global _playwright, _browser, _page
    from playwright.sync_api import sync_playwright

    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=headless,
        args=["--ignore-certificate-errors", "--disable-blink-features=AutomationControlled"],
    )
    context = _browser.new_context(
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    _page = context.new_page()
    return f"Browser started. Page ready. URL: {_page.url}"


def _do_open_url(url: str):
    """Internal: navigate to URL."""
    global _page
    _page.goto(url, wait_until="networkidle", timeout=_NAVIGATION_TIMEOUT_MS)
    _page.wait_for_timeout(3000)  # SPA settle time
    return f"Navigated to: {_page.url} | Title: {_page.title()}"


def _do_click(selector: str):
    """Internal: click element."""
    global _page
    _page.click(selector, timeout=_ACTION_TIMEOUT_MS)
    _page.wait_for_timeout(1000)
    return f"Clicked: {selector} | Current URL: {_page.url}"


def _do_fill(selector: str, value: str):
    """Internal: fill input field."""
    global _page
    # Resolve credential tokens
    resolved_value = value
    if value == "CREDENTIAL_USERNAME":
        resolved_value = os.environ.get("CREDENTIAL_USERNAME", os.environ.get("APP_USERNAME", value))
    elif value == "CREDENTIAL_PASSWORD":
        resolved_value = os.environ.get("CREDENTIAL_PASSWORD", os.environ.get("APP_PASSWORD", value))

    _page.fill(selector, resolved_value, timeout=_ACTION_TIMEOUT_MS)
    return f"Filled: {selector} with value (length={len(resolved_value)})"


def _do_select_option(selector: str, value: str = "", label: str = "", index: int = -1):
    """Internal: select dropdown option."""
    global _page
    if value:
        _page.select_option(selector, value=value, timeout=_ACTION_TIMEOUT_MS)
    elif label:
        _page.select_option(selector, label=label, timeout=_ACTION_TIMEOUT_MS)
    elif index >= 0:
        _page.select_option(selector, index=index, timeout=_ACTION_TIMEOUT_MS)
    return f"Selected option in: {selector}"


def _do_wait_for_selector(selector: str, timeout: int):
    """Internal: wait for element."""
    global _page
    _page.wait_for_selector(selector, timeout=timeout)
    return f"Element found: {selector}"


def _do_get_text(selector: str):
    """Internal: get text content of element."""
    global _page
    text = _page.text_content(selector, timeout=_ACTION_TIMEOUT_MS)
    return text or ""


def _do_get_page_content():
    """Internal: get cleaned page HTML."""
    global _page
    html = _page.content()
    # Strip scripts and styles
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Truncate
    if len(html) > 8000:
        html = html[:8000] + "\n... [truncated]"
    return html


def _do_screenshot(path: str):
    """Internal: take screenshot."""
    global _page
    _page.screenshot(path=path, full_page=True)
    return f"Screenshot saved: {path} | URL: {_page.url}"


def _do_check_browser():
    """Internal: check browser state."""
    global _page, _browser
    if _page is None or _browser is None:
        return "Browser is not running."
    return f"Browser OK | URL: {_page.url} | Title: {_page.title()}"


def _do_close_browser():
    """Internal: close browser."""
    global _playwright, _browser, _page
    if _browser:
        _browser.close()
    if _playwright:
        _playwright.stop()
    _playwright = None
    _browser = None
    _page = None
    return "Browser closed."


def _do_authenticate_aad(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str,
    target_url: str,
    method: str,
    token_login_path: str,
    token_param_name: str,
):
    """Internal: authenticate via Azure AD."""
    global _page
    import httpx

    # Get token from Azure AD
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    verify: bool | ssl.SSLContext = True
    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file and os.path.exists(cert_file):
        verify = ssl.create_default_context(cafile=cert_file)

    with httpx.Client(verify=verify, timeout=30) as client:
        resp = client.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scope,
            },
        )
        if resp.status_code != 200:
            return f"AAD token request failed: HTTP {resp.status_code} - {resp.text}"
        token_data = resp.json()
        access_token = token_data.get("access_token", "")

    if method == "header":
        # Inject Authorization header via route interception
        _page.set_extra_http_headers({"Authorization": f"Bearer {access_token}"})
        _page.goto(target_url, wait_until="networkidle", timeout=_NAVIGATION_TIMEOUT_MS)
        return f"Authenticated via header injection. URL: {_page.url}"

    elif method == "token_url":
        # Navigate to token login path
        login_url = f"{target_url.rstrip('/')}{token_login_path}?{token_param_name}={access_token}"
        _page.goto(login_url, wait_until="networkidle", timeout=_NAVIGATION_TIMEOUT_MS)
        return f"Authenticated via token URL. URL: {_page.url}"

    elif method == "easyauth":
        # Azure App Service EasyAuth
        _page.goto(target_url, wait_until="networkidle", timeout=_NAVIGATION_TIMEOUT_MS)
        auth_url = f"{target_url.rstrip('/')}/.auth/login/aad"
        resp_auth = httpx.post(
            auth_url,
            json={"access_token": access_token},
            verify=verify,
            timeout=30,
        )
        if resp_auth.status_code == 200:
            cookie = resp_auth.cookies.get("AppServiceAuthSession")
            if cookie:
                _page.context.add_cookies([{
                    "name": "AppServiceAuthSession",
                    "value": cookie,
                    "domain": target_url.split("//")[1].split("/")[0],
                    "path": "/",
                }])
            _page.reload(wait_until="networkidle")
        return f"Authenticated via EasyAuth. URL: {_page.url}"

    elif method == "msal_cache":
        # Inject MSAL cache into browser storage
        _page.goto(target_url, wait_until="networkidle", timeout=_NAVIGATION_TIMEOUT_MS)
        _page.evaluate(f"""() => {{
            sessionStorage.setItem('msal.access_token', '{access_token}');
        }}""")
        _page.reload(wait_until="networkidle")
        return f"Authenticated via MSAL cache injection. URL: {_page.url}"

    return f"Unknown auth method: {method}"


# === PUBLIC TOOL FUNCTIONS ===


@tool(approval_mode="never_require")
def start_browser(
    headless: Annotated[bool, Field(description="Run browser in headless mode")] = True,
) -> str:
    """Launch a Chromium browser instance for UI testing."""
    try:
        return _run_in_pw_thread(_do_start_browser, headless)
    except Exception as e:
        return f"Error starting browser: {e}"


@tool(approval_mode="never_require")
def open_url(
    url: Annotated[str, Field(description="The URL to navigate to")],
) -> str:
    """Navigate the browser to a URL and wait for page load."""
    try:
        return _run_in_pw_thread(_do_open_url, url)
    except Exception as e:
        return f"Error navigating to {url}: {e}"


@tool(approval_mode="never_require")
def click(
    selector: Annotated[str, Field(description="CSS or XPath selector for the element to click")],
) -> str:
    """Click an element on the page identified by CSS/XPath selector."""
    try:
        return _run_in_pw_thread(_do_click, selector)
    except Exception as e:
        return f"Error clicking {selector}: {e}"


@tool(approval_mode="never_require")
def fill(
    selector: Annotated[str, Field(description="CSS selector for the input field")],
    value: Annotated[str, Field(description="Value to fill. Use CREDENTIAL_USERNAME or CREDENTIAL_PASSWORD for credential resolution")],
) -> str:
    """Fill a text input field with a value. Supports credential token resolution."""
    try:
        return _run_in_pw_thread(_do_fill, selector, value)
    except Exception as e:
        return f"Error filling {selector}: {e}"


@tool(approval_mode="never_require")
def select_option(
    selector: Annotated[str, Field(description="CSS selector for the dropdown")],
    value: Annotated[str, Field(description="Option value attribute")] = "",
    label: Annotated[str, Field(description="Option visible text")] = "",
    index: Annotated[int, Field(description="Option index (0-based)")] = -1,
) -> str:
    """Select an option from a dropdown by value, label, or index."""
    try:
        return _run_in_pw_thread(_do_select_option, selector, value, label, index)
    except Exception as e:
        return f"Error selecting option in {selector}: {e}"


@tool(approval_mode="never_require")
def wait_for_selector(
    selector: Annotated[str, Field(description="CSS/XPath selector to wait for")],
    timeout: Annotated[int, Field(description="Timeout in milliseconds")] = 30000,
) -> str:
    """Wait for an element to appear on the page."""
    try:
        return _run_in_pw_thread(_do_wait_for_selector, selector, timeout)
    except Exception as e:
        return f"Error waiting for {selector}: {e}"


@tool(approval_mode="never_require")
def get_text(
    selector: Annotated[str, Field(description="CSS selector to get text from")],
) -> str:
    """Get the text content of a page element."""
    try:
        return _run_in_pw_thread(_do_get_text, selector)
    except Exception as e:
        return f"Error getting text from {selector}: {e}"


@tool(approval_mode="never_require")
def get_page_content() -> str:
    """Get the current page HTML content (scripts/styles stripped, max 8000 chars)."""
    try:
        return _run_in_pw_thread(_do_get_page_content)
    except Exception as e:
        return f"Error getting page content: {e}"


@tool(approval_mode="never_require")
def screenshot(
    path: Annotated[str, Field(description="File path to save screenshot")] = "screenshot.png",
) -> str:
    """Take a full-page screenshot and save to file."""
    try:
        return _run_in_pw_thread(_do_screenshot, path)
    except Exception as e:
        return f"Error taking screenshot: {e}"


@tool(approval_mode="never_require")
def check_browser() -> str:
    """Check if the browser is running and return current URL/title."""
    try:
        return _run_in_pw_thread(_do_check_browser)
    except Exception as e:
        return f"Error checking browser: {e}"


@tool(approval_mode="never_require")
def close_browser() -> str:
    """Close the browser and cleanup resources."""
    try:
        return _run_in_pw_thread(_do_close_browser)
    except Exception as e:
        return f"Error closing browser: {e}"


@tool(approval_mode="never_require")
def authenticate_aad(
    tenant_id: Annotated[str, Field(description="Azure AD tenant ID")],
    client_id: Annotated[str, Field(description="Azure AD application (client) ID")],
    client_secret: Annotated[str, Field(description="Azure AD client secret")],
    scope: Annotated[str, Field(description="OAuth2 scope for token request")],
    target_url: Annotated[str, Field(description="The application URL to authenticate against")],
    method: Annotated[str, Field(description="Auth injection method: header, token_url, easyauth, msal_cache")] = "header",
    token_login_path: Annotated[str, Field(description="Path for token_url method")] = "/auth/token",
    token_param_name: Annotated[str, Field(description="Query parameter name for token_url method")] = "token",
) -> str:
    """Authenticate to an application using Azure AD service principal credentials."""
    try:
        return _run_in_pw_thread(
            _do_authenticate_aad,
            tenant_id, client_id, client_secret, scope, target_url,
            method, token_login_path, token_param_name,
        )
    except Exception as e:
        return f"Error during AAD authentication: {e}"


# All browser tools for export
BROWSER_TOOLS = [
    start_browser,
    open_url,
    click,
    fill,
    select_option,
    wait_for_selector,
    get_text,
    get_page_content,
    screenshot,
    check_browser,
    close_browser,
    authenticate_aad,
]
