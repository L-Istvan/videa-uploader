"""Package boundaries, independent SRT handling, and the CLI contract."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from videa_uploader import cli
from videa_uploader._srt import parse_subtitle, format_subtitle
from videa_uploader._storage import default_session_path
from videa_uploader.session import open_upload


class StandaloneTests(unittest.TestCase):
    def test_cli_passes_each_tag_as_one_string(self):
        with patch('videa_uploader.cli.upload_video', return_value='https://videa.hu/video') as upload, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['upload', 'video.mp4', '--title', 'Title',
                '--tag', 'Series 25 rész', '--tag', 'Series 25 magyar felirattal']), 0)
            self.assertEqual(upload.call_args.kwargs['tags'], ['Series 25 rész', 'Series 25 magyar felirattal'])

    def test_force_upload_and_subtitle_use_same_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            srt = Path(tmp) / 'hu.srt'
            srt.write_text('1\n00:00:01,000 --> 00:00:03,000\nSzia!\n')
            with patch('videa_uploader.cli.upload_video', return_value='url') as upload, patch('videa_uploader.cli.attach_subtitle') as subtitle, redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['upload', '1.webm', '--title', 'Test', '--force',
                                           '--headless', '--state', str(Path(tmp) / 'state.json'),
                                           '--subtitle', str(srt)]), 0)
                self.assertTrue(upload.call_args.kwargs['force'])
                self.assertTrue(upload.call_args.kwargs['headless'])
                self.assertEqual(upload.call_args.kwargs['state_path'], subtitle.call_args.kwargs['state_path'])

    def test_srt_normalization_does_not_require_translation_modules(self):
        text = '\ufeff8\r\n00:00:01,000 --> 00:00:03,000\r\nSzia!\r\n'
        self.assertEqual(format_subtitle(parse_subtitle(text)),
                         '8\n00:00:01,000 --> 00:00:03,000\nSzia!')
        for bad in ('', '1\n00:00:03,000 --> 00:00:01,000\nText',
                    '1\n00:61:00,000 --> 00:62:00,000\nText'):
            with self.subTest(text=bad), self.assertRaises(ValueError):
                parse_subtitle(bad)

    def test_default_session_is_not_inside_installed_package(self):
        with patch.dict('os.environ', {'XDG_CONFIG_HOME': '/tmp/test-videa-config'}):
            self.assertEqual(default_session_path(), Path('/tmp/test-videa-config/videa-uploader/session.json'))

    def test_manual_login_never_calls_upload(self):
        with patch('videa_uploader.cli.save_login') as login, patch('videa_uploader.cli.upload_video') as upload:
            self.assertEqual(cli.main(['--session', '/tmp/session.json', 'login']), 0)
            login.assert_called_once_with(session_path=Path('/tmp/session.json'))
            upload.assert_not_called()

    def test_upload_can_be_followed_by_subtitle_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            srt = Path(tmp) / 'hu.srt'
            srt.write_text('1\n00:00:01,000 --> 00:00:03,000\nSzia!\n')
            calls = []
            with patch('videa_uploader.cli.upload_video', side_effect=lambda *a, **k: calls.append('upload') or 'https://videa.hu/video'), patch('videa_uploader.cli.attach_subtitle', side_effect=lambda *a, **k: calls.append('subtitle')), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['upload', 'video.mp4', '--title', 'Example', '--subtitle', str(srt)]), 0)
            self.assertEqual(calls, ['upload', 'subtitle'])

    def test_subtitle_command_does_not_upload_video(self):
        with patch('videa_uploader.cli.attach_subtitle') as subtitle, patch('videa_uploader.cli.upload_video') as upload:
            self.assertEqual(cli.main(['--session', '/tmp/session.json', 'subtitle', 'video.mp4', 'hu.srt', '--state', '/tmp/state.json']), 0)
            subtitle.assert_called_once_with(Path('video.mp4'), Path('hu.srt'), name='Magyar',
                session_path=Path('/tmp/session.json'), state_path=Path('/tmp/state.json'))
            upload.assert_not_called()

    def test_exit_codes_for_failure_and_interrupt(self):
        with patch('videa_uploader.cli.save_login', side_effect=RuntimeError('failed')), patch('sys.stderr'):
            self.assertEqual(cli.main(['login']), 1)
        with patch('videa_uploader.cli.save_login', side_effect=KeyboardInterrupt):
            self.assertEqual(cli.main(['login']), 130)

    def test_invalid_subtitle_stops_before_video_upload(self):
        with tempfile.TemporaryDirectory() as tmp, patch('videa_uploader.cli.upload_video') as upload, patch('sys.stderr'):
            subtitle = Path(tmp) / 'invalid.srt'
            subtitle.write_text('not an SRT')
            self.assertEqual(cli.main(['upload', 'video.mp4', '--title', 'Example', '--subtitle', str(subtitle)]), 1)
            upload.assert_not_called()

    def test_library_does_not_implicitly_read_credentials_from_environment(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        page.url = 'https://videa.hu/belepes/feltoltes'
        with patch.dict('os.environ', {'VIDEA_EMAIL': 'test@example.com', 'VIDEA_PASSWORD': 'secret'}):
            with self.assertRaisesRegex(RuntimeError, 'login'):
                open_upload(page)
        page.locator.return_value.fill.assert_not_called()
