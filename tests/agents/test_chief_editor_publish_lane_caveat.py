from agents.chief_editor.tools import _apply_lane_caveat


def test_apply_lane_caveat_adds_prefix_for_developing_brief() -> None:
    source = {
        "synth_metadata": {
            "publication": {
                "publication_lane": "developing_brief",
            }
        }
    }

    title, summary, body = _apply_lane_caveat(
        source,
        "City Officials Share Initial Findings",
        "Authorities released an early summary.",
        "Body content",
    )

    assert title.startswith("Developing: ")
    assert "developing brief" in summary.lower()
    assert body == "Body content"


def test_apply_lane_caveat_is_noop_for_verified_story() -> None:
    source = {
        "synth_metadata": {
            "publication": {
                "publication_lane": "verified_story",
            }
        }
    }

    title, summary, body = _apply_lane_caveat(
        source,
        "Officials Confirm Updated Details",
        "A concise verified summary.",
        "Body content",
    )

    assert title == "Officials Confirm Updated Details"
    assert summary == "A concise verified summary."
    assert body == "Body content"


def test_apply_lane_caveat_is_idempotent_for_existing_prefix() -> None:
    source = {
        "synth_metadata": {
            "publication": {
                "publication_lane": "developing_brief",
            }
        }
    }

    title, summary, _ = _apply_lane_caveat(
        source,
        "Developing: Officials Provide Update",
        "This is a developing brief and details may change as new reporting is verified. Existing summary.",
        "Body content",
    )

    assert title == "Developing: Officials Provide Update"
    assert summary.count("developing brief") == 1
