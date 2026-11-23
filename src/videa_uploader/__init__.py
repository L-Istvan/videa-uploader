"""Unofficial Videa uploader; independent of any series or translation project."""
from .session import save_login
from .upload import upload_video
from .subtitles import attach_subtitle

__all__ = ['save_login', 'upload_video', 'attach_subtitle']
__version__ = '0.1.0'
