"""Top-level package for Hades II Run Tracker."""

__author__ = """Zachary Myers"""
__email__ = "zachmyers@woosterbrush.com"

from .app import app, create_app

__all__ = ["app", "create_app"]
