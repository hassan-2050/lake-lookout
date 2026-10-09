from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import make_memo, make_photo, needs_ffmpeg
from lookout import ingest
from lookout.ingest import Memo, Photo, group

UTC = timezone.utc


def test_gps_and_time_round_trip(tmp_path):
    p = ingest.read_photo(make_photo(tmp_path / "a.jpg", gps=(27.9, 86.925, 5010.0),
                                     offset="+05:45"))
    assert p.lat == pytest.approx(27.9, abs=1e-5)
    assert p.lon == pytest.approx(86.925, abs=1e-5)
    assert p.alt_m == pytest.approx(5010.0)
    assert p.time_source == "photo EXIF"
    # 09:15 at UTC+05:45 is 03:30 UTC
    assert p.time == datetime(2026, 10, 10, 3, 30, tzinfo=UTC)


def test_southern_and_western_hemispheres_are_negative(tmp_path):
    p = ingest.read_photo(make_photo(tmp_path / "b.jpg", gps=(-9.39, -77.38, 4560.0)))
    assert p.lat == pytest.approx(-9.39, abs=1e-5)
    assert p.lon == pytest.approx(-77.38, abs=1e-5)


def test_photo_without_gps_has_no_location_not_a_crash(tmp_path):
    p = ingest.read_photo(make_photo(tmp_path / "c.jpg", gps=None))
    assert (p.lat, p.lon, p.alt_m) == (None, None, None)


def test_zeroed_gps_fix_is_treated_as_no_fix(tmp_path):
    p = ingest.read_photo(make_photo(tmp_path / "d.jpg", gps=(0.0, 0.0, 0.0)))
    assert p.lat is None and p.lon is None


def test_photo_without_exif_time_falls_back_to_file_date(tmp_path):
    p = ingest.read_photo(make_photo(tmp_path / "e.jpg", when=None))
    assert p.time_source == "file modified date"


def test_time_from_recorder_file_names():
    t = ingest.time_from_filename("Recording_20261010_091530.m4a")
    assert t is not None and t.astimezone(ingest.local_zone()).replace(tzinfo=None) == \
        datetime(2026, 10, 10, 9, 15, 30)
    assert ingest.time_from_filename("New Recording 3.m4a") is None


@needs_ffmpeg
def test_memo_time_comes_from_audio_metadata_in_utc(tmp_path):
    m = ingest.read_memo(make_memo(tmp_path / "memo.m4a", "2026-10-10T04:16:00Z"))
    assert m.time == datetime(2026, 10, 10, 4, 16, tzinfo=UTC)
    assert m.time_source == "audio metadata"
    assert m.duration_s == pytest.approx(2.0, abs=0.2)


@needs_ffmpeg
def test_utc_memo_pairs_with_local_photo_across_the_offset(tmp_path):
    """The bug this guards: EXIF is local time, memo metadata is UTC.

    A naive comparison puts the memo hours away from the photo it describes.
    """
    make_photo(tmp_path / "lake.jpg", when="2026:10:10 09:15:00", offset="+05:00")
    make_memo(tmp_path / "memo.m4a", "2026-10-10T04:16:30Z")   # 09:16:30 at UTC+5
    stops = ingest.scan(tmp_path)
    assert len(stops) == 1
    assert [m.path.name for m in stops[0].memos] == ["memo.m4a"]


def _photo(minute, lat=27.9, lon=86.92, name=None):
    t = datetime(2026, 10, 10, 9, 0, tzinfo=UTC) + timedelta(minutes=minute)
    return Photo(Path(name or f"p{minute}.jpg"), t, "photo EXIF", lat, lon, None)


def _memo(minute, name=None):
    t = datetime(2026, 10, 10, 9, 0, tzinfo=UTC) + timedelta(minutes=minute)
    return Memo(Path(name or f"m{minute}.m4a"), t, "audio metadata", 10.0)


def test_photos_close_in_time_and_space_form_one_stop():
    stops = group([_photo(0), _photo(2)], [])
    assert len(stops) == 1 and len(stops[0].photos) == 2


def test_photos_far_apart_in_time_are_separate_stops():
    stops = group([_photo(0), _photo(20)], [])
    assert [s.id for s in stops] == ["S01", "S02"]


def test_photos_close_in_time_but_far_apart_are_separate_stops():
    # 0.01 degrees of latitude is about 1.1 km
    stops = group([_photo(0), _photo(3, lat=27.91)], [])
    assert len(stops) == 2


def test_memo_pairs_with_the_nearest_stop():
    stops = group([_photo(0), _photo(30)], [_memo(1), _memo(33)])
    assert [m.path.name for m in stops[0].memos] == ["m1.m4a"]
    assert [m.path.name for m in stops[1].memos] == ["m33.m4a"]


def test_memo_with_no_photo_nearby_becomes_a_voice_only_stop():
    stops = group([_photo(0)], [_memo(45)])
    assert len(stops) == 2
    assert stops[1].photos == [] and len(stops[1].memos) == 1
    assert stops[1].location is None
