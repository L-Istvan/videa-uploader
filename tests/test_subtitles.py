"""Feliratcsatolás, állapotmentés és ismételt feltöltés elleni védelem."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import videa_uploader.subtitles as v


SRT = '1\n00:00:01,000 --> 00:00:03,000\nSzia!\n'
VCODE = 'abcdefghijkl1234'


def response(data):
    result = MagicMock(ok=True)
    result.json.return_value = {'response': data}
    return result


class SubtitleUploadTests(unittest.TestCase):
    def files(self, directory):
        video, subtitle, session = [Path(directory) / p for p in ('video.mp4', 'hu.srt', 'session.json')]
        video.write_bytes(b'video')
        subtitle.write_text(SRT)
        session.write_text('{}')
        stat = video.stat()
        state = {'status': 'complete', 'vcode': VCODE,
                 'file': {'path': str(video.resolve()), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}}
        video.with_suffix('.videa.json').write_text(json.dumps(state))
        return video, subtitle, session

    def test_srt_is_validated_saved_and_reused_without_second_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            request = playwright.return_value.__enter__.return_value.request.new_context.return_value
            request.post.side_effect = [response({'code': 0}), response({'code': 0, 'st_id': 123})]
            self.assertEqual(v.attach_subtitle(video, subtitle, session_path=session), 123)
            commands = [json.loads(call.kwargs['form']['json']) for call in request.post.call_args_list]
            self.assertEqual([c['cmd'] for c in commands], ['validateVideoSubtitleByRequest', 'addVideoSubtitleByRequest'])
            self.assertEqual(commands[1]['vcode'], VCODE)
            self.assertEqual(commands[1]['name'], 'Magyar')
            self.assertEqual(commands[1]['srt'], SRT)
            self.assertEqual(commands[1]['shift'], 0)
            self.assertEqual(v.attach_subtitle(video, subtitle, session_path=session), 123)
            self.assertEqual(request.post.call_count, 2)
            self.assertEqual(playwright.call_count, 1)
            request.dispose.assert_called_once()
            record = json.loads(video.with_suffix('.videa.json').read_text())['subtitles']['Magyar']
            self.assertEqual(record['status'], 'complete')

    def test_uncertain_addition_is_not_automatically_repeated(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            request = playwright.return_value.__enter__.return_value.request.new_context.return_value
            request.post.side_effect = [response({'code': 0}), v.PlaywrightError('timeout')]
            with self.assertRaisesRegex(RuntimeError, 'időtúllépés'):
                v.attach_subtitle(video, subtitle, session_path=session)
            state = json.loads(video.with_suffix('.videa.json').read_text())
            self.assertEqual(state['status'], 'complete')  # A videó feltöltése továbbra is kész.
            self.assertEqual(state['subtitles']['Magyar']['status'], 'attaching')
            with self.assertRaisesRegex(RuntimeError, 'bizonytalan'):
                v.attach_subtitle(video, subtitle, session_path=session)
            self.assertEqual(request.post.call_count, 2)

    def test_server_validation_error_does_not_send_addition(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            request = playwright.return_value.__enter__.return_value.request.new_context.return_value
            request.post.return_value = response({'code': 2})
            with self.assertRaisesRegex(RuntimeError, 'szerverhibakód 2'):
                v.attach_subtitle(video, subtitle, session_path=session)
            request.post.assert_called_once()
            self.assertNotIn('subtitles', json.loads(video.with_suffix('.videa.json').read_text()))

    def test_invalid_local_srt_does_not_call_server(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            subtitle.write_text('not an SRT')
            with self.assertRaises(ValueError):
                v.attach_subtitle(video, subtitle, session_path=session)
            playwright.assert_not_called()

    def test_changed_srt_is_not_added_as_a_second_hungarian_track(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            request = playwright.return_value.__enter__.return_value.request.new_context.return_value
            request.post.side_effect = [response({'code': 0}), response({'code': 0, 'st_id': 123})]
            v.attach_subtitle(video, subtitle, session_path=session)
            subtitle.write_text(SRT.replace('Szia!', 'Helló!'))
            with self.assertRaisesRegex(RuntimeError, 'eltérő'):
                v.attach_subtitle(video, subtitle, session_path=session)
            self.assertEqual(request.post.call_count, 2)

    def test_addition_without_valid_id_remains_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            request = playwright.return_value.__enter__.return_value.request.new_context.return_value
            request.post.side_effect = [response({'code': 0}), response({'code': 0})]
            with self.assertRaisesRegex(RuntimeError, 'feliratazonosítót'):
                v.attach_subtitle(video, subtitle, session_path=session)
            state = json.loads(video.with_suffix('.videa.json').read_text())
            self.assertEqual(state['subtitles']['Magyar']['status'], 'attaching')

    def test_explicit_state_path_is_shared_without_touching_video_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.subtitles.sync_playwright') as playwright:
            video, subtitle, session = self.files(tmp)
            target = Path(tmp) / 'receipts' / 'upload.json'
            target.parent.mkdir()
            video.with_suffix('.videa.json').rename(target)
            request = playwright.return_value.__enter__.return_value.request.new_context.return_value
            request.post.side_effect = [response({'code': 0}), response({'code': 0, 'st_id': 123})]
            v.attach_subtitle(video, subtitle, session_path=session, state_path=target)
            self.assertEqual(json.loads(target.read_text())['subtitles']['Magyar']['status'], 'complete')
            self.assertFalse(video.with_suffix('.videa.json').exists())
