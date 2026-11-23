"""Authentication; credentials and sessions never live in the installed package."""
import re
from urllib.parse import urlparse
from pathlib import Path
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, sync_playwright
from ._storage import atomic_json, default_session_path

HOME = 'https://videa.hu'
SESSION = default_session_path()


def accept_cookies(page):
    try:
        page.get_by_role('button', name='ELFOGADOM', exact=True).click(timeout=2000)
    except PlaywrightTimeout:
        pass  # A korábban elfogadott banner nem jelenik meg újra.

def open_upload(page, *, email=None, password=None):
    page.goto(HOME + '/feltoltes', wait_until='domcontentloaded')
    accept_cookies(page)
    if urlparse(page.url).path.startswith('/belepes'):
        if not email or not password:
            raise RuntimeError('Videa-belépés szükséges: videa-uploader login')
        try:
            page.locator('#login-email').fill(email)
            page.locator('#login-password').fill(password)
            page.locator('#form-login').get_by_role('button', name='Belépés', exact=True).click()
            page.wait_for_url(re.compile(r'https://videa\.hu/feltoltes(?:[/?#]|$)'), timeout=60000)
        except PlaywrightError:
            # A Playwright hívásnaplójában a fill() értéke is szerepelhetne.
            raise RuntimeError('A Videa-belépés sikertelen. Próbáld a videa-uploader login parancsot.') from None
    page.locator('#upFile').wait_for(state='attached')

def save_login(session_path=SESSION):
    """Kézi bejelentkezés; jelszó nem kell a kódba és nem kerül a naplóba."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context(locale='hu-HU')
            page = context.new_page()
            page.goto(HOME + '/feltoltes', wait_until='domcontentloaded')
            accept_cookies(page)
            print('Jelentkezz be a böngészőben. A feltöltőoldal megjelenésekor mentem a munkamenetet.', flush=True)
            page.locator('#upFile').wait_for(state='attached', timeout=300000)
            atomic_json(Path(session_path).expanduser(), context.storage_state())
            print('A Videa-munkamenet elmentve. Fájl nem lett feltöltve.')
        finally:
            browser.close()
