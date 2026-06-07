"""Available conversion profiles."""

from __future__ import annotations

from .base import ConversionProfile
from .fitelnet import FitelnetProfile
from .generic import GenericProfile
from .srs import SrsProfile


PROFILES: dict[str, ConversionProfile] = {
    "generic": GenericProfile(),
    "fitelnet": FitelnetProfile(),
    "srs": SrsProfile(),
}
PROFILE_NAMES = tuple(PROFILES)


def get_profile(name: str) -> ConversionProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(PROFILE_NAMES)
        raise ValueError(
            f"未知のプロファイルです: {name}（選択肢: {choices}）"
        ) from exc


__all__ = ["PROFILE_NAMES", "ConversionProfile", "get_profile"]
