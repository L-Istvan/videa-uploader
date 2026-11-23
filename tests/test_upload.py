"""Videa-feltöltés tesztjei hamis böngészővel, külső műveletek nélkül."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from playwright.sync_api import TimeoutError as PlaywrightTimeout

import videa_uploader.upload as u


VCODE = 'abcdefghijkl1234'
PARAMS = {'upload_url': 'https://upload.videa.hu/upload', 'maxfilesize': 1000,
          'upload_limit_bytes': 2000, 'upload_limit_seconds': 7200}


def response(data, *, ok=True):
    result = MagicMock(ok=ok)
    result.status = 200 if ok else 500
    result.json.return_value = {'response': data}
    return result


class UploadTests(unittest.TestCase):
    def test_force_preserves_previous_state_and_uploads_again(self):
        for status in ('complete', 'transferring'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
                video = Path(tmp) / 'video.webm'
                video.write_bytes(b'video')
                target = Path(tmp) / 'custom.json'
                previous = json.dumps({'file': {}, 'status': status, 'url': 'old-url'})
                target.write_text(previous)
                _, page = self.setup_browser(playwright)
                transfer, saved = MagicMock(), MagicMock()
                transfer.value = response({'code': 0, 'vcode': VCODE})
                saved.value = response({'code': 0})
                page.expect_response.return_value.__enter__.side_effect = [transfer, saved]
                url = u.upload_video(video, title='New title', force=True, headless=True,
                                     state_path=target, session_path=Path(tmp) / 'session.json')
                self.assertEqual(url, u.HOME + '/player?v=' + VCODE)
                backups = list(Path(tmp).glob('custom.backup-*.json'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(), previous)
                self.assertEqual(json.loads(target.read_text())['status'], 'complete')
                page.locator.return_value.set_input_files.assert_called_once_with(str(video))
                playwright.return_value.__enter__.return_value.chromium.launch.assert_called_once_with(headless=True)

    def setup_browser(self, playwright):
        browser = playwright.return_value.__enter__.return_value.chromium.launch.return_value
        context = browser.new_context.return_value
        context.storage_state.return_value = {'cookies': [], 'origins': []}
        page = context.new_page.return_value
        page.url = u.HOME + '/feltoltes'
        page.locator.return_value.all_text_contents.return_value = [
            'page = new VIDEA.pages.feltoltes(' + json.dumps(PARAMS) + ');']
        return browser, page

    def test_parameters_are_read_from_real_page_shape(self):
        self.assertEqual(u.upload_parameters(['unrelated',
            'page = new VIDEA.pages.feltoltes(' + json.dumps(PARAMS) + ');']), PARAMS)
        with self.assertRaisesRegex(RuntimeError, 'beállításai'):
            u.upload_parameters(['page = new VIDEA.pages.other({"a":1});'])

    def test_success_requires_both_responses_and_restart_does_not_launch_browser(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
            video = Path(tmp) / 'episode.mp4'
            video.write_bytes(b'video')
            session = Path(tmp) / 'session.json'
            browser, page = self.setup_browser(playwright)
            transfer = MagicMock()
            transfer.value = response({'code': 0, 'vcode': VCODE})
            saved = MagicMock()
            saved.value = response({'code': 0})
            page.expect_response.return_value.__enter__.side_effect = [transfer, saved]
            url = u.upload_video(video, title='Test episode', session_path=session)
            self.assertEqual(url, u.HOME + '/player?v=' + VCODE)
            state = json.loads(video.with_suffix('.videa.json').read_text())
            self.assertEqual(state['status'], 'complete')
            self.assertEqual(page.expect_response.call_count, 2)
            browser.close.assert_called_once()
            self.assertEqual(session.stat().st_mode & 0o777, 0o600)
            u.upload_video(video, title='Test episode', session_path=session)
            self.assertEqual(playwright.call_count, 1)

    def test_uncertain_transfer_is_not_retried_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
            video = Path(tmp) / 'episode.mp4'
            video.write_bytes(b'video')
            _, page = self.setup_browser(playwright)
            page.expect_response.return_value.__enter__.side_effect = PlaywrightTimeout('timeout')
            with self.assertRaisesRegex(RuntimeError, 'időkorlátot'):
                u.upload_video(video, title='Test', session_path=Path(tmp) / 'session.json')
            self.assertEqual(json.loads(video.with_suffix('.videa.json').read_text())['status'], 'transferring')
            with self.assertRaisesRegex(RuntimeError, 'bizonytalan'):
                u.upload_video(video, title='Test')
            self.assertEqual(playwright.call_count, 1)

    def test_save_failure_keeps_video_id_and_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
            video = Path(tmp) / 'episode.mp4'
            video.write_bytes(b'video')
            _, page = self.setup_browser(playwright)
            transfer, saved = MagicMock(), MagicMock()
            transfer.value = response({'code': 0, 'vcode': VCODE})
            saved.value = response({'code': 4})
            page.expect_response.return_value.__enter__.side_effect = [transfer, saved]
            with self.assertRaisesRegex(RuntimeError, 'adatlapmentés.*4'):
                u.upload_video(video, title='Test', session_path=Path(tmp) / 'session.json')
            state = json.loads(video.with_suffix('.videa.json').read_text())
            self.assertEqual(state['status'], 'publishing')
            self.assertEqual(state['vcode'], VCODE)

    def test_changed_video_is_not_treated_as_previously_uploaded(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
            video = Path(tmp) / 'episode.mp4'
            video.write_bytes(b'changed')
            video.with_suffix('.videa.json').write_text(json.dumps(
                {'file': {}, 'status': 'complete', 'url': 'https://videa.hu/player?v=' + VCODE}))
            with self.assertRaisesRegex(RuntimeError, 'megváltozott'):
                u.upload_video(video, title='Test')
            playwright.assert_not_called()

    def test_no_login_or_changed_page_does_not_reserve_a_transfer(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
            video = Path(tmp) / 'episode.mp4'
            video.write_bytes(b'video')
            self.setup_browser(playwright)
            with patch('videa_uploader.upload.open_upload', side_effect=RuntimeError('Login required')):
                with self.assertRaises(RuntimeError):
                    u.upload_video(video, title='Test')
            self.assertFalse(video.with_suffix('.videa.json').exists())

    def test_size_limit_stops_before_file_selection(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
            video = Path(tmp) / 'episode.mp4'
            video.write_bytes(b'x' * 2000)
            _, page = self.setup_browser(playwright)
            with self.assertRaisesRegex(ValueError, 'méretkorlátját'):
                u.upload_video(video, title='Test', session_path=Path(tmp) / 'session.json')
            page.expect_response.assert_not_called()
            page.locator.return_value.set_input_files.assert_not_called()
            self.assertFalse(video.with_suffix('.videa.json').exists())

    def test_login_error_never_exposes_password_in_exception(self):
        page = MagicMock()
        page.url = u.HOME + '/belepes/feltoltes'
        page.locator.return_value.fill.side_effect = u.PlaywrightError('secret-password-in-call-log')
        with patch.dict('os.environ', {'VIDEA_EMAIL': 'test@example.com', 'VIDEA_PASSWORD': 'secret'}):
            with self.assertRaises(RuntimeError) as error:
                u.open_upload(page, email='test@example.com', password='secret')
        self.assertNotIn('secret', str(error.exception))

    def test_invalid_responses_never_mean_success(self):
        for data, ok in (({'code': 8}, True), ({}, True), ({'code': 0}, False)):
            with self.subTest(data=data, ok=ok), self.assertRaises(RuntimeError):
                u.checked_response(response(data, ok=ok), 'test')

    def test_save_matcher_rejects_other_requests(self):
        r = MagicMock()
        r.request.method = 'POST'
        r.url = 'https://videa.hu/interface?logcmd=shareThisByRequest'
        self.assertTrue(u.is_save_response(r))
        r.url = 'https://videa.hu/interface?logcmd=other'
        self.assertFalse(u.is_save_response(r))

    def test_save_matcher_accepts_videakid_response(self):
        r = MagicMock()
        r.request.method = 'POST'
        r.url = 'https://videakid.hu/interface?logcmd=shareThisByRequest'
        self.assertTrue(u.is_save_response(r))

    def test_only_exact_video_link_from_known_domains_confirms_save(self):
        correct = 'https://videakid.hu/videok/animacio/test-' + VCODE
        self.assertEqual(u.saved_video_url(f'<a href="{correct}">Teszt</a>', VCODE), correct)
        self.assertIsNone(u.saved_video_url(f'<a href="https://other.example/videok/a/test-{VCODE}">Teszt</a>', VCODE))
        self.assertIsNone(u.saved_video_url('<a href="/videok/a/test-othercode">Teszt</a>', VCODE))
        self.assertIsNone(u.saved_video_url('<p>' + VCODE + '</p>', VCODE))

    def test_save_timeout_is_success_only_if_video_is_in_own_list(self):
        for found in (True, False):
            with self.subTest(found=found), tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.upload.sync_playwright') as playwright:
                video = Path(tmp) / 'episode.mp4'
                video.write_bytes(b'video')
                browser, page = self.setup_browser(playwright)
                transfer = MagicMock()
                transfer.value = response({'code': 0, 'vcode': VCODE})
                page.expect_response.return_value.__enter__.side_effect = [transfer, PlaywrightTimeout('timeout')]
                url = 'https://videa.hu/videok/film-animacio/test-' + VCODE
                listing = browser.new_context.return_value.request.get.return_value
                listing.ok = True
                listing.text.return_value = f'<a href="{url}">Test</a>' if found else '<p>Más videók</p>'
                if found:
                    self.assertEqual(u.upload_video(video, title='Test', session_path=Path(tmp) / 'session.json'), url)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'publishing'):
                        u.upload_video(video, title='Test', session_path=Path(tmp) / 'session.json')
                state = json.loads(video.with_suffix('.videa.json').read_text())
                self.assertEqual(state['status'], 'complete' if found else 'publishing')
                self.assertEqual(page.expect_response.call_count, 2)

    def test_metadata_selects_regular_videa_film_category(self):
        page = MagicMock()
        u.fill_metadata(page, 'Test', '')
        page.get_by_label.return_value.select_option.assert_called_once_with('0')
        page.locator.assert_any_call('#category_select')
        page.locator.return_value.select_option.assert_called_once_with(label='film/animáció')
