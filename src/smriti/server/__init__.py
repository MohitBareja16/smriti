"""Smriti FastAPI server exposing Chat/SSE, Threads, Vault, Samarth, PYQ, and Syllabus APIs."""

from __future__ import annotations

from smriti.server.app import create_app

__all__ = ["create_app"]
