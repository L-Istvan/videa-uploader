"""Unofficial Videa browser upload and receipt verification."""
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError, sync_playwright
from ._storage import atomic_json
from .session import HOME, SESSION, open_upload


def upload_parameters(scripts):
    """A bejelentkezett oldal tényleges feltöltési címe és fiókkorlátai."""
    for script in scripts:
        for match in re.finditer(r'new\s+VIDEA\.pages\.\w+\s*\(\s*', script):
            try:
                params, _ = json.JSONDecoder().raw_decode(script[match.end():])
            except ValueError:
                continue
            if isinstance(params, dict) and params.get('upload_url'):
                return params
    raise RuntimeError('A Videa feltöltési beállításai nem találhatók; az oldal megváltozhatott.')

def check_upload_limits(video, params):
    size = video.stat().st_size
    if size < params['maxfilesize']:
        return
    if size >= params['upload_limit_bytes']:
        raise ValueError('A videó meghaladja a Videa-fiók feltöltési méretkorlátját.')
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        raise RuntimeError('A nagy videó időkorlátjának ellenőrzéséhez ffprobe szükséges.')
    result = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'default=noprint_wrappers=1:nokey=1', str(video)],
                            check=True, capture_output=True, text=True, timeout=30)
    duration = float(result.stdout.strip())
    if not 0 < duration < params['upload_limit_seconds']:
        raise ValueError('A videó meghaladja a Videa-fiók nagy fájlokra vonatkozó időkorlátját.')

def checked_response(response, action):
    if not response.ok:
        raise RuntimeError(f'Videa {action}: HTTP {response.status}.')
    try:
        data = response.json()['response']
        code = data['code']
    except (ValueError, KeyError, TypeError):
        raise RuntimeError(f'Videa {action}: ismeretlen szerverválasz.') from None
    if code != 0:
        raise RuntimeError(f'Videa {action}: szerverhibakód {code}.')
    return data

def normalize_tags(tags):
    if isinstance(tags, str):
        raise ValueError('A tags paraméter szövegek listája legyen, ne egyetlen szöveg.')
    result = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip() or re.search(r'[\x00-\x1f,<>\"]', tag):
            raise ValueError('A címke nem lehet üres, és nem tartalmazhat vesszőt, idézőjelet vagy vezérlőkaraktert.')
        tag = tag.strip()
        if tag not in result:
            result.append(tag)
    return result


def fill_metadata(page, title, description, *, category='film/animáció', tags=()):
    page.get_by_label('Tartalom típusa:').select_option('0')
    page.locator('#title').fill(title)
    page.locator('.se-wrapper-inner.se-wrapper-wysiwyg').fill(description)
    page.locator('#category_select').select_option(label=category)
    if tags:
        field = page.get_by_role('textbox', name='Címkék:', exact=True)
        for tag in tags:
            field.fill(tag)
            field.press('Enter')
        registered = page.locator('.videa-keyword[data-value]').evaluate_all(
            '(nodes) => nodes.map(node => node.getAttribute("data-value"))')
        if not set(tags).issubset(registered):
            raise RuntimeError('A Videa nem vette át az összes megadott címkét.')
    page.locator('#paidpromotion-no').check()
    read_terms = page.get_by_role('button', name='Elolvasom', exact=True)
    if read_terms.is_visible():
        read_terms.click()
        page.get_by_role('button', name='Popup bezárása', exact=True).click()
    page.locator('input[name="copyright"]').check()

def is_save_response(response):
    url = urlparse(response.url)
    return (url.hostname in ('videa.hu', 'www.videa.hu', 'videakid.hu', 'www.videakid.hu')
            and url.path == '/interface'
            and parse_qs(url.query).get('logcmd') == ['shareThisByRequest']
            and response.request.method == 'POST')

def saved_video_url(html, vcode):
    """Csak a konkrét videóazonosító saját listában talált linkje bizonyít sikeres mentést."""
    for link in BeautifulSoup(html, 'html.parser').find_all('a', href=True):
        href = urljoin(HOME, link['href'])
        url = urlparse(href)
        if url.hostname not in ('videa.hu', 'www.videa.hu', 'videakid.hu', 'www.videakid.hu'):
            continue
        if (url.path.startswith('/videok/') and url.path.endswith('-' + vcode)
                or url.path == '/player' and parse_qs(url.query).get('v') == [vcode]):
            return href
    return None

def upload_video(video, *, title, description='', headless=False,
                 timeout_seconds=7200, session_path=SESSION, email=None, password=None, category='film/animáció', state_path=None, force=False, tags=()):
    """Az eredeti MP4-et küldi fel; nem éget rá és nem csatol külön feliratot.

    A force=True archiválja a korábbi állapotot és új feltöltést indít.
    Egyébként bizonytalan korábbi kísérletet nem ismétel meg. A .videa.json fájlt csak a
    saját Videa-videólistád ellenőrzése után szabad kézzel törölni vagy javítani.
    """
    video = Path(video).expanduser().resolve()
    if not video.is_file() or not video.stat().st_size:
        raise ValueError(f'A feltöltendő videó hiányzik vagy üres: {video}')
    if not title.strip() or timeout_seconds <= 0:
        raise ValueError('Nem üres cím és pozitív feltöltési időkorlát szükséges.')
    tags = normalize_tags(tags)
    stat = video.stat()
    identity = {'path': str(video), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    state_path = Path(state_path).expanduser().resolve() if state_path is not None else video.with_suffix('.videa.json')
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if force and state_path.exists():
        backup = state_path.with_name(f'{state_path.stem}.backup-{uuid4().hex}{state_path.suffix}')
        state_path.rename(backup)
        print(f'Videa: kényszerített új feltöltés; a korábbi állapot mentése: {backup}', flush=True)
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state.get('file') != identity:
            raise RuntimeError(f'A videó megváltozott a feltöltési mentéshez képest: {state_path}')
        if state.get('status') == 'complete' and state.get('url'):
            print(f'A videó már fel lett töltve, kihagyva: {state["url"]}\n'
                  'Az új cím és leírás ilyenkor nem módosítja a meglévő videót. '
                  'Ezeket a Videa webes felületén szerkesztheted.', flush=True)
            return state['url']
        raise RuntimeError(f'Korábbi Videa-feltöltés eredménye bizonytalan ({state.get("status")}). '
                           f'Ellenőrizd a saját videóidat és ezt a mentést: {state_path}')

    session_path = Path(session_path).expanduser()
    # Az x mód a párhuzamos feltöltés véletlen elindítását is megakadályozza.
    state = {'file': identity, 'status': 'preparing'}
    with state_path.open('x', encoding='utf-8') as file:
        json.dump(state, file)
    try:
        print('Videa: böngésző indítása' + (' háttérben...' if headless else '...'), flush=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                context = browser.new_context(locale='hu-HU', storage_state=str(session_path) if session_path.exists() else None)
                page = context.new_page()
                page.set_default_timeout(30000)
                print('Videa: feltöltőoldal megnyitása és bejelentkezés ellenőrzése...', flush=True)
                open_upload(page, email=email, password=password)
                atomic_json(session_path, context.storage_state())
                params = upload_parameters(page.locator('script:not([src])').all_text_contents())
                check_upload_limits(video, params)
                upload_url = urljoin(page.url, params['upload_url'])
                state['status'] = 'transferring'
                atomic_json(state_path, state)
                print(f'Videa: fájl feltöltése ({stat.st_size / 1_000_000_000:.2f} GB)...', flush=True)
                with page.expect_response(lambda r: r.url == upload_url and r.request.method == 'POST',
                                          timeout=timeout_seconds * 1000) as pending:
                    page.locator('#upFile').set_input_files(str(video))
                uploaded = checked_response(pending.value, 'fájlfeltöltés')
                vcode = uploaded.get('vcode', '')
                if not isinstance(vcode, str) or not re.fullmatch(r'[A-Za-z0-9]{16}', vcode):
                    raise RuntimeError('A Videa nem adott érvényes videóazonosítót.')
                state.update(status='uploaded', vcode=vcode, url=HOME + '/player?v=' + vcode)
                atomic_json(state_path, state)
                print('Videa: a fájlátvitel kész, a videóadatok kitöltése...', flush=True)
                fill_metadata(page, title, description, category=category, tags=tags)
                state['status'] = 'publishing'
                atomic_json(state_path, state)
                print('Videa: a fájlátvitel kész, az adatlap mentése következik...', flush=True)
                try:
                    with page.expect_response(is_save_response, timeout=60000) as pending:
                        page.get_by_role('button', name='Mentés', exact=True).click()
                    checked_response(pending.value, 'adatlapmentés')
                except PlaywrightError:
                    # Átirányításkor elveszhet az XHR-válasz. Nem mentünk újra:
                    # előbb csak olvasással ellenőrizzük a konkrét videóazonosítót.
                    listing = context.request.get(HOME + '/videoim', timeout=30000)
                    confirmed = saved_video_url(listing.text(), vcode) if listing.ok else None
                    if not confirmed:
                        raise
                    state['url'] = confirmed
                state['status'] = 'complete'
                atomic_json(state_path, state)
                return state['url']
            finally:
                browser.close()
    except PlaywrightError as error:
        raise RuntimeError('A Videa böngészős lépése sikertelen vagy túllépte az időkorlátot. '
                           f'Lépés: {state["status"]}; hibatípus: {type(error).__name__}. '
                           f'A kísérlet állapota: {state_path}') from None
    finally:
        if state['status'] == 'preparing':
            state_path.unlink(missing_ok=True)  # Eddig még nem küldtünk fel fájlt.
