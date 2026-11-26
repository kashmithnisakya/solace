"""Crisis resources shown to people at risk.

IMPORTANT: verify every number with the organisation before each release.
Last checked: 2026-11 (unverified, please confirm before launch).
"""

from pydantic import BaseModel


class Resource(BaseModel):
    name: str
    contact: str
    description: str
    hours: str = ""
    url: str = ""


_BY_REGION: dict[str, list[Resource]] = {
    "LK": [
        Resource(
            name="National Mental Health Helpline",
            contact="1926",
            hours="24/7",
            description="Free, confidential support from the National Institute of Mental Health.",
        ),
        Resource(
            name="Sumithrayo",
            contact="011 2696666",
            url="https://sumithrayo.org",
            description="Emotional support for people who are struggling or thinking about suicide.",
        ),
        Resource(
            name="CCCline",
            contact="1333",
            hours="24/7",
            url="https://ccclk.org",
            description="Free crisis support line from the CCC Foundation.",
        ),
        Resource(
            name="Emergency (Police)",
            contact="119",
            hours="24/7",
            description="If you or someone else is in immediate danger.",
        ),
        Resource(
            name="Suwa Seriya Ambulance",
            contact="1990",
            hours="24/7",
            description="Free emergency ambulance service.",
        ),
    ],
}

_INTERNATIONAL = Resource(
    name="Find A Helpline",
    contact="findahelpline.com",
    url="https://findahelpline.com",
    description="Free, confidential crisis lines in most countries.",
)


def resources_for(region: str) -> list[Resource]:
    return [*_BY_REGION.get(region.upper(), []), _INTERNATIONAL]
