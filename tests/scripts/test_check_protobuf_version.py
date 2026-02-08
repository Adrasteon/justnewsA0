try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover
    import importlib_metadata  # type: ignore


def parse_version(ver: str):
    parts = [int(x) for x in ver.split(".") if x.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def test_protobuf_version_meets_minimum():
    min_ver = (4, 24, 0)
    try:
        import google.protobuf as pb

        v = getattr(pb, "__version__", None) or getattr(pb, "version", None)
        if not v:
            v = importlib_metadata.version("protobuf")
    except Exception:
        # If not installed in CI, skip this test
        import pytest

        pytest.skip("protobuf not installed in test environment")

    ver_tuple = parse_version(v)
    assert ver_tuple >= min_ver, f"protobuf version {v} is lower than {min_ver}"
