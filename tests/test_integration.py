"""Integration tests for Headscale HA addon.

Tests the real addon Docker image with all services (headscale, headplane, nginx)
running. Simulates HA ingress behavior by sending X-Ingress-Path headers.

Usage:
    # Build and test (default)
    python -m pytest tests/test_integration.py -v

    # Skip build (if image already exists)
    SKIP_BUILD=1 python -m pytest tests/test_integration.py -v
"""

import os
import re
import subprocess
import time

import pytest
import requests

CONTAINER_NAME = "headscale-ha-test"
NGINX_PORT = 3000
HEADSCALE_PORT = 8080
INGRESS_PATH = "/api/hassio_ingress/test_token_abc123"
IMAGE_NAME = "headscale-ha-test:latest"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Timeouts
SERVICE_TIMEOUT = 180  # seconds to wait for services to start (Headplane can take ~100s)
REQUEST_TIMEOUT = 10  # seconds per HTTP request


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture(scope="session", autouse=True)
def addon_container():
    """Build the addon image, start the container, wait for services, yield, cleanup."""

    # Build
    if not os.environ.get("SKIP_BUILD"):
        print("\n--- Building addon image ---")
        result = subprocess.run(
            [
                "docker",
                "build",
                "--build-arg",
                "BUILD_FROM=ghcr.io/hassio-addons/base:20.0.1",
                "--build-arg",
                "BUILD_ARCH=amd64",
                "-t",
                IMAGE_NAME,
                os.path.join(PROJECT_ROOT, "headscale"),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.exit(f"Docker build failed:\n{result.stderr}", returncode=1)

    # Cleanup any previous run
    docker("rm", "-f", CONTAINER_NAME, check=False)

    # Start container with INGRESS_ENTRY env var for nginx template
    print("--- Starting addon container ---")
    docker(
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        "-p",
        f"{NGINX_PORT}:{NGINX_PORT}",
        "-p",
        f"{HEADSCALE_PORT}:{HEADSCALE_PORT}",
        "-e",
        f"INGRESS_ENTRY={INGRESS_PATH}",
        "-v",
        f"{PROJECT_ROOT}/tests/options.json:/data/options.json:ro",
        IMAGE_NAME,
    )

    # Wait for headscale
    print("--- Waiting for Headscale ---")
    _wait_for_service(f"http://localhost:{HEADSCALE_PORT}/health", "Headscale")

    # Wait for nginx/headplane
    print("--- Waiting for Headplane/nginx ---")
    _wait_for_service(f"http://localhost:{NGINX_PORT}/login", "nginx/Headplane")

    # Extract API key from container logs
    api_key = _extract_api_key()
    print(f"--- API key extracted: {api_key[:20]}... ---")

    yield {"api_key": api_key}

    # Cleanup
    print("\n--- Collecting container logs ---")
    logs = docker("logs", CONTAINER_NAME, check=False)
    print(logs.stdout[-2000:] if len(logs.stdout) > 2000 else logs.stdout)
    if logs.stderr:
        print(logs.stderr[-1000:] if len(logs.stderr) > 1000 else logs.stderr)

    print("--- Stopping container ---")
    docker("rm", "-f", CONTAINER_NAME, check=False)


def _wait_for_service(url: str, name: str):
    deadline = time.time() + SERVICE_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 500:
                print(f"  {name} ready (status {r.status_code})")
                return
        except (requests.ConnectionError, requests.ReadTimeout, requests.Timeout):
            pass
        time.sleep(3)
    # Dump logs on failure
    logs = docker("logs", "--tail", "50", CONTAINER_NAME, check=False)
    pytest.exit(
        f"{name} did not become ready within {SERVICE_TIMEOUT}s.\n"
        f"Container logs:\n{logs.stdout}\n{logs.stderr}",
        returncode=1,
    )


def _extract_api_key() -> str:
    """Extract the API key from container logs."""
    deadline = time.time() + 30
    while time.time() < deadline:
        logs = docker("logs", CONTAINER_NAME, check=False)
        for line in logs.stdout.splitlines():
            match = re.search(r"(hskey-api-\S+)", line)
            if match:
                return match.group(1)
        time.sleep(2)
    pytest.exit("Could not extract API key from container logs", returncode=1)


def ingress_get(path: str, **kwargs) -> requests.Response:
    """GET request simulating HA ingress (prefix stripped, header set)."""
    headers = kwargs.pop("headers", {})
    headers["X-Ingress-Path"] = INGRESS_PATH
    return requests.get(
        f"http://localhost:{NGINX_PORT}{path}",
        headers=headers,
        allow_redirects=False,
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )


def ingress_post(path: str, **kwargs) -> requests.Response:
    """POST request simulating HA ingress."""
    headers = kwargs.pop("headers", {})
    headers["X-Ingress-Path"] = INGRESS_PATH
    return requests.post(
        f"http://localhost:{NGINX_PORT}{path}",
        headers=headers,
        allow_redirects=False,
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )


def direct_get(path: str, **kwargs) -> requests.Response:
    """GET request without ingress (direct access)."""
    return requests.get(
        f"http://localhost:{NGINX_PORT}{path}",
        allow_redirects=False,
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )


# ============================================================
# Service Health Tests
# ============================================================


class TestServiceHealth:
    def test_headscale_health(self):
        r = requests.get(
            f"http://localhost:{HEADSCALE_PORT}/health", timeout=REQUEST_TIMEOUT
        )
        assert r.status_code == 200

    def test_nginx_listening(self):
        r = direct_get("/login")
        assert r.status_code == 200

    def test_headplane_serves_pages(self):
        r = direct_get("/login")
        assert r.status_code == 200
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


# ============================================================
# Ingress Root Redirect Tests
# ============================================================


class TestIngressRedirect:
    def test_root_redirects_to_machines(self):
        r = ingress_get("/")
        assert r.status_code == 302

    def test_root_redirect_includes_ingress_prefix(self):
        r = ingress_get("/")
        location = r.headers.get("Location", "")
        assert INGRESS_PATH in location, f"Location header: {location}"
        assert location.endswith("/machines"), f"Location header: {location}"


# ============================================================
# Ingress URL Rewriting Tests (sub_filter)
# ============================================================


class TestIngressRewriting:
    def test_basename_rewritten(self):
        r = ingress_get("/login")
        assert f'"basename":"{INGRESS_PATH}/"' in r.text, (
            f"basename not rewritten. Body snippet: {r.text[:500]}"
        )

    def test_window_baseurl_injected(self):
        r = ingress_get("/login")
        assert f'window.baseUrl="{INGRESS_PATH}/"' in r.text

    def test_href_rewritten(self):
        r = ingress_get("/login")
        # All href="/ should become href="$INGRESS_PATH/
        hrefs = re.findall(r'href="(/[^"]*)"', r.text)
        for href in hrefs:
            assert href.startswith(INGRESS_PATH) or href.startswith("http"), (
                f"href not rewritten: {href}"
            )

    def test_src_rewritten(self):
        r = ingress_get("/login")
        srcs = re.findall(r'src="(/[^"]*)"', r.text)
        for src in srcs:
            assert src.startswith(INGRESS_PATH) or src.startswith("http"), (
                f"src not rewritten: {src}"
            )

    def test_ingress_path_not_empty(self):
        """Verify ingress path is hardcoded in sub_filter output, not empty.

        Problem 17-18: nginx variables don't expand in sub_filter.
        The fix uses sed to hardcode the ingress path at startup.
        """
        r = direct_get("/login")
        # window.baseUrl MUST contain the full ingress path, not just "/"
        assert f'window.baseUrl="{INGRESS_PATH}/"' in r.text, (
            f"Ingress path not hardcoded in nginx config! "
            f"Expected baseUrl containing '{INGRESS_PATH}'. "
            f"Got: {re.search(r'window.baseUrl=[^;]+', r.text).group(0) if 'window.baseUrl' in r.text else 'no baseUrl found'}"
        )
        # Double-check: basename must also have the full path
        assert f'"basename":"{INGRESS_PATH}/"' in r.text, (
            f"Ingress path not hardcoded in basename! "
            f"Got: {re.search(r'\"basename\":\"[^\"]*\"', r.text).group(0) if 'basename' in r.text else 'no basename found'}"
        )

    def test_manifest_path_not_rewritten(self):
        """manifestPath must NOT be prefixed (causes double-prefix in React Router)."""
        r = ingress_get("/login")
        # manifestPath should stay as "/__manifest", not get the ingress prefix
        assert f'"manifestPath":"{INGRESS_PATH}/' not in r.text, (
            "manifestPath was rewritten with ingress prefix - will cause double-prefix!"
        )

    def test_no_bare_asset_href_src(self):
        """No href/src attributes pointing to /assets/ without the ingress prefix."""
        r = ingress_get("/login")
        # Check href="/assets/..." and src="/assets/..." are all prefixed
        bare_hrefs = re.findall(r'href="(/assets/[^"]*)"', r.text)
        for href in bare_hrefs:
            assert False, f"Bare asset href found: href=\"{href}\""
        bare_srcs = re.findall(r'src="(/assets/[^"]*)"', r.text)
        for src in bare_srcs:
            assert False, f"Bare asset src found: src=\"{src}\""


# ============================================================
# Login Flow Tests
# ============================================================


class TestLoginFlow:
    def test_login_page_loads(self):
        r = ingress_get("/login")
        assert r.status_code == 200
        assert "api_key" in r.text

    def test_login_post_redirects(self, addon_container):
        api_key = addon_container["api_key"]
        r = ingress_post("/login", data={"api_key": api_key})
        assert r.status_code == 302, f"Expected 302, got {r.status_code}: {r.text[:300]}"

    def test_login_post_sets_cookie(self, addon_container):
        api_key = addon_container["api_key"]
        r = ingress_post("/login", data={"api_key": api_key})
        cookies = r.headers.get("Set-Cookie", "")
        assert "_hp_auth" in cookies, f"No _hp_auth cookie. Headers: {dict(r.headers)}"

    def test_login_redirect_includes_ingress_prefix(self, addon_container):
        api_key = addon_container["api_key"]
        r = ingress_post("/login", data={"api_key": api_key})
        location = r.headers.get("Location", "")
        assert INGRESS_PATH in location, f"Login redirect missing ingress prefix: {location}"

    def test_invalid_api_key_rejected(self):
        r = ingress_post("/login", data={"api_key": "invalid-key-12345"})
        # Should either return 200 (re-show login with error) or 4xx
        assert r.status_code != 302, "Invalid key should not redirect successfully"


# ============================================================
# Authenticated Page Tests
# ============================================================


class TestAuthenticatedPages:
    @pytest.fixture()
    def session_cookie(self, addon_container):
        """Login and return the session cookie."""
        api_key = addon_container["api_key"]
        r = ingress_post("/login", data={"api_key": api_key})
        cookie = r.cookies.get("_hp_auth")
        if not cookie:
            # Extract from Set-Cookie header
            set_cookie = r.headers.get("Set-Cookie", "")
            match = re.search(r"_hp_auth=([^;]+)", set_cookie)
            if match:
                cookie = match.group(1)
        assert cookie, "Could not get session cookie"
        return {"_hp_auth": cookie}

    def test_machines_page_loads(self, session_cookie):
        r = ingress_get("/machines", cookies=session_cookie)
        assert r.status_code == 200

    def test_machines_has_rewritten_assets(self, session_cookie):
        r = ingress_get("/machines", cookies=session_cookie)
        if "href=" in r.text:
            hrefs = re.findall(r'href="(/[^"]*)"', r.text)
            for href in hrefs:
                assert href.startswith(INGRESS_PATH), (
                    f"Asset not rewritten on machines page: {href}"
                )


# ============================================================
# Direct Access Tests (no ingress)
# ============================================================


class TestDirectAccess:
    def test_direct_login_works(self):
        r = direct_get("/login")
        assert r.status_code == 200

    def test_direct_access_has_hardcoded_ingress(self):
        """With hardcoded ingress path, direct access also has prefix in response body."""
        r = direct_get("/login")
        # basename is hardcoded to the ingress path (not dynamic per-request)
        assert f'"basename":"{INGRESS_PATH}/"' in r.text

    def test_direct_root_redirect(self):
        r = direct_get("/")
        assert r.status_code == 302
        location = r.headers.get("Location", "")
        # Ingress path is hardcoded, so redirect always includes it
        assert location == f"{INGRESS_PATH}/machines", f"Direct root redirect: {location}"


# ============================================================
# Asset Loading Tests
# ============================================================


class TestAssetLoading:
    @staticmethod
    def _strip_ingress(path: str) -> str:
        """Strip the hardcoded ingress prefix from a path (simulates HA Supervisor)."""
        if path.startswith(INGRESS_PATH):
            return path[len(INGRESS_PATH):]
        return path

    def test_css_assets_return_200(self):
        """Find CSS asset URLs from the login page and verify they load."""
        r = direct_get("/login")
        css_files = re.findall(r'href="(/[^"]*\.css)"', r.text)
        assert len(css_files) > 0, "No CSS files found in login page"
        for css in css_files:
            # Strip ingress prefix (simulating what HA Supervisor does)
            bare_path = self._strip_ingress(css)
            r2 = direct_get(bare_path)
            assert r2.status_code == 200, f"CSS 404: {css} (requested as {bare_path})"
            assert "text/css" in r2.headers.get("Content-Type", ""), (
                f"Wrong Content-Type for {css}: {r2.headers.get('Content-Type')}"
            )

    def test_js_assets_return_200(self):
        """Find JS asset URLs from the login page and verify they load."""
        r = direct_get("/login")
        # Look for JS in src attributes and also in JSON manifest data
        # Paths may be prefixed with ingress path (hardcoded at startup)
        js_files = re.findall(r'src="(/[^"]*\.js)"', r.text)
        js_files += re.findall(r'"(' + re.escape(INGRESS_PATH) + r'/assets/[^"]*\.js)"', r.text)
        js_files += re.findall(r'"(/assets/[^"]*\.js)"', r.text)
        # Deduplicate
        js_files = list(set(js_files))
        assert len(js_files) > 0, "No JS files found in login page"
        for js in js_files:
            bare_path = self._strip_ingress(js)
            r2 = direct_get(bare_path)
            assert r2.status_code == 200, f"JS 404: {js} (requested as {bare_path})"

    def test_ingress_css_assets_return_200(self):
        """CSS assets with ingress prefix load when prefix is stripped (like HA does)."""
        r = direct_get("/login")
        css_files = re.findall(r'href="' + re.escape(INGRESS_PATH) + r'(/[^"]*\.css)"', r.text)
        assert len(css_files) > 0, "No ingress-prefixed CSS files found"
        for css_path in css_files:
            r2 = direct_get(css_path)
            assert r2.status_code == 200, f"CSS 404 via ingress: {css_path}"
