"""Command line entry points. No implicit .env loading in library calls."""
import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from . import __version__, attach_subtitle, save_login, upload_video
from .session import SESSION


def main(argv=None):
    parser = argparse.ArgumentParser(description='Unofficial Videa video and subtitle uploader.')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--session', type=Path, default=SESSION, help='Saved login session path.')
    parser.add_argument('--env-file', type=Path, help='Explicitly load credentials from this .env file.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('login', help='Manual browser login; never uploads a file.')
    upload = commands.add_parser('upload', help='Upload a video and save its metadata.')
    upload.add_argument('video', type=Path)
    upload.add_argument('--title', required=True)
    upload.add_argument('--description', default='')
    upload.add_argument('--category', default='film/animáció', help='Exact normal-Videa category label.')
    upload.add_argument('--subtitle', type=Path, help='Optionally attach an SRT after uploading.')
    upload.add_argument('--subtitle-name', default='Magyar')
    upload.add_argument('--state', type=Path, help='Optional upload state JSON path.')
    upload.add_argument('--headless', action='store_true')
    upload.add_argument('--force', action='store_true', help='Upload again, archiving any previous state; may create a duplicate.')
    upload.add_argument('--timeout', type=int, default=7200)
    subtitle = commands.add_parser('subtitle', help='Attach an SRT to an already uploaded video.')
    subtitle.add_argument('video', type=Path)
    subtitle.add_argument('subtitle', type=Path)
    subtitle.add_argument('--name', default='Magyar')
    subtitle.add_argument('--state', type=Path)
    args = parser.parse_args(argv)
    if args.env_file:
        if not args.env_file.is_file():
            parser.error('The selected .env file does not exist.')
        load_dotenv(args.env_file, override=False)
    try:
        if args.command == 'login':
            save_login(session_path=args.session)
        elif args.command == 'upload':
            if args.subtitle:
                # Fail before uploading a large MP4 if the selected subtitle is invalid.
                from .subtitles import _load_subtitle
                _load_subtitle(args.subtitle, args.subtitle_name)
            url = upload_video(args.video, title=args.title, description=args.description,
                category=args.category, headless=args.headless, timeout_seconds=args.timeout,
                session_path=args.session, state_path=args.state, force=args.force,
                email=os.getenv('VIDEA_EMAIL'), password=os.getenv('VIDEA_PASSWORD'))
            if args.subtitle:
                attach_subtitle(args.video, args.subtitle, name=args.subtitle_name,
                                session_path=args.session, state_path=args.state)
            print(url)
        else:
            attach_subtitle(args.video, args.subtitle, name=args.name,
                            session_path=args.session, state_path=args.state)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f'Videa: {error}', file=sys.stderr)
        return 1
    return 0
