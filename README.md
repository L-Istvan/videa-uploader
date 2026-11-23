# videa-uploader

[Magyar](#magyar) · [English](#english)

---

## Magyar

**Nem hivatalos** Python-kliens videók Videára történő feltöltéséhez és SRT-feliratok
csatolásához. A Playwrightot és a Videa saját webes felületének végpontjait használja;
nem a Videa hivatalos PartnerAPI-ja, és nem áll kapcsolatban a Videával.


### Telepítés

Python 3.10 vagy újabb szükséges. A projekt könyvtárában futtasd:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m playwright install chromium
```

Az FFmpeg részét képező `ffprobe` is szükséges, ha a fiók nagy fájlokra vonatkozó
korlátja miatt ellenőrizni kell a videó hosszát. A program nem kódolja át a videókat.

### Bejelentkezési munkamenet mentése

```bash
videa-uploader login
```

Megnyílik egy látható Chromium-ablak. Jelentkezz be kézzel; a munkamenet akkor
mentődik el, amikor elérhetővé válik a feltöltési űrlap. **A bejelentkezési parancs
soha nem választ ki és nem tölt fel videót.** A kézi bejelentkezésre öt perc áll
rendelkezésre.

A munkamenet alapértelmezés szerint a telepített csomagon kívül, a
`~/.config/videa-uploader/session.json` fájlba kerül. Ha az `XDG_CONFIG_HOME` be van
állítva, a program azt veszi figyelembe. A munkamenetfájlhoz csak a tulajdonosa kap
hozzáférési jogosultságot. Egyedi elérési utat az alparancs előtt adhatsz meg:

```bash
videa-uploader --session /eleresi/ut/session.json login
```

Nem szükséges jelszót írni a forráskódba. Az opcionális `VIDEA_EMAIL` és
`VIDEA_PASSWORD` környezeti változókat a parancssori felület használja az űrlapos
bejelentkezéshez. A `.env` fájl használatát külön meg kell adni:

```bash
cp .env.example .env
# Szerkeszd a .env fájlt a saját gépeden.
videa-uploader --env-file .env upload video.mp4 --title "Példa"
```

A Pythonból hívható függvények nem töltik be a `.env` fájlokat, és nem olvasnak
automatikusan jelszót a környezetből. Szükség esetén a belépési adatokat közvetlenül
kell átadni nekik.

### Videó feltöltése

**Ez a parancs feltölti a fájlt és elmenti a videó oldalát.** A láthatóság a
feltöltési űrlap meglévő alapbeállítását követi, amely nyilvános is lehet.

```bash
videa-uploader upload video.mp4 --title "Példa" --description "Leírás"
```

Felirat csatolásához a feltöltést követően:

```bash
videa-uploader upload video.mp4 --title "Példa" --subtitle subtitles.srt --subtitle-name "Magyar"
```

Az alapértelmezett cél a normál Videa, a kategória pedig `film/animáció`. Másik
kategóriához a `--category` kapcsolóval add meg a normál feltöltési űrlapon szereplő
pontos kategórianevet. A kliens nem választja a VideaKid felületét. A böngésző
párbeszédablakait az eredeti feltöltési folyamat szerint kezeli: megnyitja a
feltételek ablakát, bejelöli a kötelező elfogadó jelölőnégyzetet, és azt választja,
hogy nincs fizetett promóció. A feliratot nem égeti bele az MP4-fájlba.

A böngésző alapértelmezés szerint látható. A `--headless` elrejti;
a `--timeout 7200` a fájlátvitel időkorlátját állítja be másodpercben. A feltöltési
korlátokat a program a bejelentkezett fiók űrlapjáról olvassa ki, nem rögzített
értékeket használ. A videóadatok mentésének szerveroldali visszaigazolása még nem
jelenti azt, hogy a Videa befejezte a videó lejátszáshoz szükséges feldolgozását.

### Ugyanazon videó ismételt feltöltése

A `--force` kapcsoló figyelmen kívül hagyja a korábbi feltöltési állapotot, és újra
feltölti a fájlt, az újonnan megadott címmel és leírással. Háttérben is használható:

```bash
videa-uploader upload "1.webm" --title "teszt 2" --description "teszt" --headless --force
```

**Ez új videót hoz létre a Videán**, a korábbit nem módosítja és nem törli.
Bizonytalan vagy megváltozott fájlhoz tartozó állapot esetén is új feltöltést indít,
ezért előtte ellenőrizd a saját videóidat, és várd meg a még futó feltöltés végét.
A régi állapotfájlt egyedi `video.videa.backup-<azonosító>.json` néven megőrzi,
a legújabb próbálkozást pedig az eredeti állapotfájlba menti. Egyedi `--state`
útvonal esetén is az adott fájl mellé készül a biztonsági másolat.
A `--subtitle` az új feltöltéshez csatolja a feliratot; egy későbbi `subtitle`
parancs szintén a legújabb állapotfájlban szereplő videót használja.
Pythonból a `force=True` paraméterrel kérhető ugyanez.
Kapcsoló nélkül megmarad az ismételt feltöltést megakadályozó ellenőrzés.

### Felirat csatolása egy meglévő feltöltéshez

```bash
videa-uploader subtitle video.mp4 subtitles.srt --name "Magyar"
```

Csak a felirat szövegét küldi el; a videót nem tölti fel újra. A helyi
SRT-ellenőrzésnek és a Videa feliratellenőrzésének is sikeresnek kell lennie.
A jelenlegi felület legfeljebb 1 MiB méretű SRT-fájlokat fogad el.

### Használat Pythonból

```python
from videa_uploader import upload_video, attach_subtitle

url = upload_video(
    "video.mp4",
    title="Példa",
    description="Leírás",
    session_path="/eleresi/ut/session.json",
)
subtitle_id = attach_subtitle(
    "video.mp4",
    "subtitles.srt",
    name="Magyar",
    session_path="/eleresi/ut/session.json",
)
```

A `save_login(session_path=...)` függvény is elérhető a kézi böngészős
bejelentkezéshez. A `python -m videa_uploader` ugyanazt a parancssori felületet
biztosítja, mint a `videa-uploader`.

### Állapotmentés és újrapróbálkozás

A `video.mp4` mellé egy `video.videa.json` nevű feltöltési állapotfájl kerül.
A feltöltési és a feliratcsatolási parancs is elfogadja a
`--state /eleresi/ut/upload.json` kapcsolót; a Python-függvényeknél a `state_path=...`
paraméter használható. Mindkét művelethez ugyanazt az állapotfájlt add meg.

- A befejezett feltöltéseket és az azonos feliratokat újabb feltöltés nélkül használja fel.
- A feltöltés és a videóadatok mentése külön visszaigazolást kap.
- Ha a videóadatok mentésének visszaigazolása elveszik, a kliens lekéri a videólistát,
  és a siker jelzése előtt ellenőrzi a pontos videóazonosítót.
- A bizonytalan kimenetelű próbálkozásokat nem ismétli meg automatikusan. Az
  állapotfájl törlése vagy javítása előtt ellenőrizd a videólistádat.
- Megváltozott videófájl vagy ugyanazon mentett feliratnévhez tartozó eltérő felirat
  esetén külön döntés szükséges; a program nem tesz közzé automatikusan másolatokat.

Az állapotformátum kompatibilis maradt azzal a feltöltővel, amelyből ez a projekt
készült: egy meglévő `.videa.json` fájl külön megadható úgy, hogy a videó az eredeti
helyén marad. Ez a tároló nem tartalmaz munkameneteket, belépési adatokat, videókat,
feliratfájlokat vagy feltöltési visszaigazolásokat.

### Fejlesztés

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

A tesztek ideiglenes fájlokat és szimulált böngésző-/HTTP-válaszokat használnak.
Nem jelentkeznek be, nem hívnak élő szolgáltatásokat, és nem tesznek közzé videókat.
A CI ugyanazokat a teszteket futtatja Python 3.10, 3.12 és 3.14 alatt.
Az oldalhoz kapcsolódó hibaüzenetek jelenleg magyar nyelvűek.

Felépítés:

```text
src/videa_uploader/
    session.py     # Bejelentkezés és munkamenet-kezelés
    upload.py      # Videófeltöltés és szerveroldali visszaigazolás
    subtitles.py   # SRT-felirat csatolása
    _srt.py        # Önálló SRT-feldolgozó
    _storage.py    # Állapotfájlok atomi mentése
    cli.py         # Parancssori felület
tests/
```

Az önálló csomag leválasztása során nem történt élő feltöltés. Az eredeti
videófeltöltési és feliratcsatolási folyamatokat a leválasztás előtt kipróbálták;
az önálló csomag ellenőrzése külső mellékhatások nélkül történik.

---

## English

An **unofficial** Python client for uploading videos to Videa and attaching SRT
subtitles. It uses Playwright and the endpoints used by Videa's own web interface;
it is not Videa's official PartnerAPI and is not affiliated with Videa.

### Install

Requires Python 3.10 or newer. From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m playwright install chromium
```

`ffprobe` (part of FFmpeg) is also required when the account's large-file limit
requires checking the video's duration. The library does not transcode videos.

### Save a login session

```bash
videa-uploader login
```

A visible Chromium window opens. Sign in manually; the session is saved when
the upload form becomes available. **The login command never selects or uploads
a video.** It allows five minutes for manual login.

By default, the session is saved outside the installed package at
`~/.config/videa-uploader/session.json`, respecting `XDG_CONFIG_HOME` when set.
The session file is written with owner-only permissions. An explicit session
path can be supplied before the subcommand:

```bash
videa-uploader --session /path/to/session.json login
```

Passwords are not required in source code. Optional `VIDEA_EMAIL` and
`VIDEA_PASSWORD` environment variables are used by the CLI for form login.
To use a `.env` file, load it explicitly:

```bash
cp .env.example .env
# Edit .env locally.
videa-uploader --env-file .env upload video.mp4 --title "Example"
```

Library functions do not load `.env` files or implicitly read passwords from
the environment. They accept credentials explicitly when needed.

### Upload a video

**This command uploads the file and saves its video page.** Visibility follows
the upload form's existing default, which may be public.

```bash
videa-uploader upload video.mp4 --title "Example" --description "Description"
```

To attach a subtitle after uploading:

```bash
videa-uploader upload video.mp4 --title "Example" --subtitle subtitles.srt --subtitle-name "Magyar"
```

The default destination is normal Videa, category `film/animáció`. Use
`--category` with another exact category label supported by the normal upload
form. This client does not select VideaKid. Browser dialogs are handled following
the original upload flow: it opens the terms dialog, checks the required
acceptance box, and selects no paid promotion. It does not burn subtitles into
the MP4.

The browser is visible by default. `--headless` hides it; `--timeout 7200` sets
the file-transfer timeout in seconds. Upload limits are read from the logged-in
account's form, not hardcoded. Server acknowledgement of metadata saving does
not guarantee that Videa has finished processing the video for playback.

### Upload the same video again

Use `--force` to ignore previous upload state and upload the file again with the
new title and description. It also works in headless mode:

```bash
videa-uploader upload "1.webm" --title "Test 2" --description "Test" --headless --force
```

**This creates a new video on Videa**; it does not edit or delete the previous one.
It also bypasses uncertain attempts and changed-file checks, so check your video
list first and wait for any running upload to finish. The previous state is
preserved as `video.videa.backup-<identifier>.json`, while the latest attempt uses
the original state path. With a custom `--state`, the backup is placed beside that
file. `--subtitle` attaches to the new upload; subsequent `subtitle` commands also
use the video recorded in the latest state file. Python callers can pass
`force=True`. Without this option, duplicate-upload checks remain enabled.

### Attach subtitles to an existing upload

```bash
videa-uploader subtitle video.mp4 subtitles.srt --name "Magyar"
```

Only the subtitle text is sent. The video is not uploaded again. Local SRT
validation and Videa's subtitle validation must both succeed; SRT files are
limited to 1 MiB by the current interface.

### Use from Python

```python
from videa_uploader import upload_video, attach_subtitle

url = upload_video(
    "video.mp4",
    title="Example",
    description="Description",
    session_path="/path/to/session.json",
)
subtitle_id = attach_subtitle(
    "video.mp4",
    "subtitles.srt",
    name="Magyar",
    session_path="/path/to/session.json",
)
```

`save_login(session_path=...)` is also exported for manual browser login.
`python -m videa_uploader` provides the same CLI as `videa-uploader`.

### State and retries

An upload state file named `video.videa.json` is stored beside `video.mp4`.
Both upload and subtitle commands accept `--state /path/to/upload.json`; Python
functions accept `state_path=...`. Use the same state path for both operations.

- Completed uploads and identical subtitles are reused without another upload.
- Uploading and metadata saving are acknowledged separately.
- If metadata acknowledgement is lost, the client reads the video list and
  checks the exact video identifier before reporting success.
- Uncertain attempts are not retried automatically. Check your video list before
  removing or correcting their state file.
- Changed video files or different subtitles under the same saved track name
  require an explicit decision instead of automatically publishing duplicates.

The state format remains compatible with the extracted uploader: an existing
`.videa.json` can be selected explicitly while keeping the video at its original
path. No sessions, credentials, videos, subtitle files, or upload receipts are
included in this repository.

### Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests use temporary files and mocked browser/HTTP responses. They do not log
in, call live services, or publish videos. CI runs the same tests on Python
3.10, 3.12, and 3.14. Site errors currently use Hungarian messages.

Layout:

```text
src/videa_uploader/
    session.py     # Login and session handling
    upload.py      # Video upload and server acknowledgement
    subtitles.py   # SRT attachment
    _srt.py        # Independent SRT parser
    _storage.py    # Atomic state files
    cli.py         # Command line interface
tests/
```

The standalone package has not performed a live upload during extraction.
Its original video-upload and subtitle-attachment flows were exercised before
extraction; the independent package is verified without external side effects.
