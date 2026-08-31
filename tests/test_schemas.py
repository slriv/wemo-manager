"""Unit tests for app.schemas validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import SetStateRequest


def test_on_alone_is_valid():
    assert SetStateRequest(on=True).on is True


def test_level_alone_is_valid():
    assert SetStateRequest(level=50).level == 50


def test_neither_on_nor_level_is_invalid():
    with pytest.raises(ValidationError):
        SetStateRequest()
