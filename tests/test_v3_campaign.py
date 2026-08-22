from luminary_leads.config import load_config


def test_v3_campaign_is_isolated_and_has_five_personalised_steps():
    config = load_config("config/landscaper_lead_engine.yaml")
    route = config["instantly_deep_research_v3"]
    sequence = load_config("config/instantly_landscaper_deep_research_v3_sequence.yaml")

    assert route["campaign_id"] == "fe2e8779-0486-473b-a5b4-fa11512ee542"
    assert route["required_research_mode"] == "deep_research_v3"
    steps = sequence["sequences"][0]["steps"]
    assert len(steps) == 5
    assert "personalised_subject_line" in steps[0]["variants"][0]["subject"]
    assert "icebreaker" in steps[0]["variants"][0]["body"]
    assert "target_customer_angle" in steps[1]["variants"][0]["body"]
    assert "differentiators" in steps[2]["variants"][0]["body"]
