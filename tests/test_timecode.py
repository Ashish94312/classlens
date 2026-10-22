from classlens.timecode import format_time, parse_time


def test_format_time():
    assert format_time(65) == "01:05"
    assert format_time(3725) == "1:02:05"


def test_parse_time():
    assert parse_time("[01:05]") == 65
    assert parse_time("1:02:05") == 3725
    assert parse_time("around 12:31–13:00") == 751
    assert parse_time("n/a") is None
