# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The human surface: root serves the UI, and the UI explains itself.

Regression guard for the first-visitor failure: landing on / used to
return {"detail": "Not Found"}, and the page offered raw JSON with no
plain-language guidance. The UI's surface copy is part of the product
(the simplicity rule: plain words up front, jargon one layer down).
"""

from fastapi.testclient import TestClient

from spine.api import create_app


def test_root_serves_the_ui() -> None:
    client = TestClient(create_app())
    root = client.get("/")
    assert root.status_code == 200
    assert "TransformationSpine" in root.text
    ui = client.get("/ui")
    assert ui.status_code == 200
    assert root.text == ui.text


def test_ui_explains_itself_in_plain_words() -> None:
    client = TestClient(create_app())
    text = client.get("/ui").text
    # The one obvious action, with an example already filled in.
    assert "Try it" in text
    assert "What would you like it to do?" in text
    assert "Run it" in text
    # The verdict is rendered in words, not only as JSON.
    assert "Accepted" in text
    assert "Not accepted" in text
    # The record check explains itself before the button.
    assert "Check the record" in text
    assert "tamper-evident" in text
    # Jargon lives one layer down, in the developers section.
    assert "For developers" in text
    assert "/api/v1/transform" in text
