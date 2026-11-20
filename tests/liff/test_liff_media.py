from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from line_group_agent.itinerary.itinerary_image_store import ItineraryImageStore
from line_group_agent.liff.liff_router import build_liff_router

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=timezone(timedelta(hours=9)))
PNG = b"\x89PNG\r\n\x1a\nfake"


def client_of(
    tmp_path: Path, *, with_images: bool = True
) -> tuple[TestClient, ItineraryImageStore]:
    store = ItineraryImageStore(tmp_path, lambda: NOW)
    app = FastAPI()
    app.include_router(
        build_liff_router(
            "<html></html>",
            None,  # type: ignore[arg-type]
            max_body_bytes=1024,
            images=store if with_images else None,
        )
    )
    return TestClient(app), store


def test_an_image_is_served_as_a_png_that_may_be_kept_a_day_without_a_login(
    tmp_path: Path,
) -> None:
    client, store = client_of(tmp_path)
    name = store.save("Cgroup", PNG)
    response = client.get(f"/liff/media/{name}")
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_a_name_nobody_was_given_is_not_found(tmp_path: Path) -> None:
    client, store = client_of(tmp_path)
    store.save("Cgroup", PNG)
    for name in ("a" * 22 + ".png", "short.png", "..%2F..%2Fsecret.png", "x" * 22 + ".jpg"):
        assert client.get(f"/liff/media/{name}").status_code == 404


def test_without_an_image_store_there_is_no_route(tmp_path: Path) -> None:
    client, store = client_of(tmp_path, with_images=False)
    name = store.save("Cgroup", PNG)
    assert client.get(f"/liff/media/{name}").status_code == 404
