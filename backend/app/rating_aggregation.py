"""Rating summary and web-prior blending rules."""

from __future__ import annotations

from typing import Optional


WEB_RATING_PRIOR_COUNT = 20


def blend_movie_rating(
    web_average: Optional[float],
    site_average: Optional[float],
    site_count: int,
) -> Optional[float]:
    if site_count <= 0 or site_average is None:
        return web_average
    if web_average is None:
        return site_average

    prior_count = WEB_RATING_PRIOR_COUNT
    return (
        float(web_average) * prior_count + float(site_average) * site_count
    ) / (prior_count + site_count)
