from line_group_agent.itinerary.image_slicing import ImageSlice, slice_days


def test_days_that_fit_together_make_one_image_from_the_top_of_the_page() -> None:
    blocks = [(100.0, 600.0), (600.0, 1100.0)]
    assert slice_days(blocks, max_height=2000, max_count=3) == [ImageSlice(0.0, 1100.0, 2)]


def test_a_day_that_would_pass_the_limit_starts_the_next_image() -> None:
    blocks = [(100.0, 1300.0), (1300.0, 2500.0), (2500.0, 3700.0)]
    assert slice_days(blocks, max_height=2400, max_count=3) == [
        ImageSlice(0.0, 1300.0, 1),
        ImageSlice(1300.0, 3700.0, 2),
    ]


def test_a_day_taller_than_the_limit_is_an_image_of_its_own() -> None:
    blocks = [(100.0, 3000.0), (3000.0, 3500.0)]
    assert slice_days(blocks, max_height=2400, max_count=3) == [
        ImageSlice(0.0, 3000.0, 1),
        ImageSlice(3000.0, 3500.0, 1),
    ]


def test_days_past_the_most_images_are_left_out() -> None:
    blocks = [(100.0 + 2000 * i, 2100.0 + 2000 * i) for i in range(5)]
    slices = slice_days(blocks, max_height=2400, max_count=3)
    assert len(slices) == 3
    assert sum(piece.day_count for piece in slices) == 3


def test_no_days_make_no_images() -> None:
    assert slice_days([], max_height=2400, max_count=3) == []
