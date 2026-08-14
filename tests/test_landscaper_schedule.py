from datetime import date

from luminary_leads.landscaper_schedule import (
    Location,
    expected_scheduled_cron,
    load_locations,
    location_for_date,
)


def test_location_files_form_one_deduplicated_queue():
    locations = load_locations(
        [
            "data/landscaper_locations/uk_towns_cities_over_20000.csv",
            "data/landscaper_locations/london_boroughs_over_20000.csv",
        ]
    )

    assert len(locations) == 560
    assert locations[0].name == "Birmingham"
    assert locations[527].name == "Hazlemere"
    assert locations[528].name == "Croydon"
    assert locations[-1].name == "Kensington and Chelsea"
    assert len({location.name.casefold() for location in locations}) == 560


def test_location_selection_advances_daily_and_cycles():
    locations = [Location("Birmingham", "towns.csv"), Location("Glasgow", "towns.csv")]

    assert location_for_date(locations, date(2026, 8, 15), date(2026, 8, 15)).name == "Birmingham"
    assert location_for_date(locations, date(2026, 8, 16), date(2026, 8, 15)).name == "Glasgow"
    assert location_for_date(locations, date(2026, 8, 17), date(2026, 8, 15)).name == "Birmingham"


def test_expected_cron_keeps_eight_am_across_clock_changes():
    assert expected_scheduled_cron(
        date(2026, 8, 15), timezone="Europe/London", local_hour=8
    ) == "0 7 * * *"
    assert expected_scheduled_cron(
        date(2026, 12, 15), timezone="Europe/London", local_hour=8
    ) == "0 8 * * *"
