"""Session-only username helpers for The Secret Number.

This is deliberately not an account system: a name only identifies the
current browser session and is cleared when the app is refreshed.
"""
import streamlit as st


def current_user() -> str | None:
    return st.session_state.get("username")


def sign_in(username: str) -> bool:
    """Store a simple display name for this browser session."""
    username = username.strip()
    if not username:
        return False
    st.session_state.username = username[:30]
    return True


def sign_out() -> None:
    st.session_state.pop("username", None)
