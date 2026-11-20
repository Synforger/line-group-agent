from line_group_agent.itinerary.itinerary import ItineraryItem
from line_group_agent.liff.day_layout import layout_day


def item(item_id: str, start: str | None, end: str | None = None) -> ItineraryItem:
    return ItineraryItem(item_id, 1, f"item {item_id}", start, end)


def placed(*items: ItineraryItem) -> dict[str, tuple[int, int, int, int, int]]:
    layout = layout_day(items)
    assert layout is not None
    return {
        band.item.id: (band.start_min, band.end_min, band.bottom_min, band.column, band.columns)
        for band in layout.bands
    }


def test_a_day_without_a_timed_item_has_no_layout() -> None:
    assert layout_day([]) is None
    assert layout_day([item("a", None)]) is None


def test_a_band_runs_from_its_start_to_its_end() -> None:
    assert placed(item("a", "09:00", "10:30")) == {"a": (540, 630, 630, 0, 1)}


def test_an_item_without_an_end_takes_an_hour() -> None:
    assert placed(item("a", "09:00")) == {"a": (540, 600, 600, 0, 1)}


def test_an_item_that_starts_in_the_last_hour_of_the_day_stops_at_midnight() -> None:
    assert placed(item("a", "23:30")) == {"a": (1410, 1440, 1440, 0, 1)}


def test_a_short_item_is_drawn_at_least_half_an_hour_long_but_keeps_its_end() -> None:
    assert placed(item("a", "09:00", "09:10")) == {"a": (540, 550, 570, 0, 1)}


def test_the_axis_reaches_an_hour_around_the_items_on_half_hour_lines() -> None:
    layout = layout_day([item("a", "09:15", "10:10"), item("b", "13:00", "14:20")])
    assert layout is not None
    assert (layout.axis_start_min, layout.axis_end_min) == (480, 930)


def test_the_axis_stays_inside_the_day() -> None:
    early = layout_day([item("a", "00:10", "00:40")])
    late = layout_day([item("a", "23:00", "23:50")])
    assert early is not None and late is not None
    assert early.axis_start_min == 0 and late.axis_end_min == 1440


def test_items_that_overlap_share_the_width_in_columns() -> None:
    result = placed(item("a", "09:00", "11:00"), item("b", "10:00", "11:30"))
    assert result["a"][3:] == (0, 2) and result["b"][3:] == (1, 2)


def test_items_that_only_touch_do_not_overlap() -> None:
    result = placed(item("a", "09:00", "10:00"), item("b", "10:00", "11:00"))
    assert result["a"][3:] == (0, 1) and result["b"][3:] == (0, 1)


def test_a_free_column_is_used_again_and_the_run_is_as_wide_as_its_widest_moment() -> None:
    result = placed(
        item("a", "09:00", "12:00"),
        item("b", "09:30", "10:30"),
        item("c", "10:30", "11:30"),
        item("d", "11:00", "11:45"),
    )
    assert result["a"][3:] == (0, 3)
    assert result["b"][3:] == (1, 3)
    assert result["c"][3:] == (1, 3)
    assert result["d"][3:] == (2, 3)


def test_two_runs_of_a_day_are_laid_out_apart() -> None:
    result = placed(
        item("a", "09:00", "10:00"),
        item("b", "09:30", "10:30"),
        item("c", "14:00", "15:00"),
    )
    assert result["c"][3:] == (0, 1) and result["a"][4] == result["b"][4] == 2


def test_overlap_is_judged_on_the_drawn_length_so_no_two_bands_cover_each_other() -> None:
    result = placed(item("a", "09:00", "09:10"), item("b", "09:20", "10:00"))
    assert result["a"][3:] == (0, 2) and result["b"][3:] == (1, 2)


def test_items_without_a_time_are_left_out_of_the_axis() -> None:
    layout = layout_day([item("a", None), item("b", "09:00", "10:00")])
    assert layout is not None and [band.item.id for band in layout.bands] == ["b"]
