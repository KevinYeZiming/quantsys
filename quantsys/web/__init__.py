"""Quantsys web interfaces — Flask desktop app + Streamlit dashboard."""

from quantsys.web.app import app as flask_app, main as desktop_main

__all__ = ["flask_app", "desktop_main"]
