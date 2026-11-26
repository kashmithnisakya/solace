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


# Sinhala names and descriptions, keyed by contact. Numbers never change with language.
_SINHALA: dict[str, tuple[str, str]] = {
    "1926": ("ජාතික මානසික සෞඛ්‍ය උපකාරක සේවය", "ජාතික මානසික සෞඛ්‍ය ආයතනයෙන් නොමිලේ, රහසිගත සහාය."),
    "011 2696666": ("සුමිත්‍රයෝ", "අමාරුවෙන් ඉන්න, නැත්නම් සියදිවි නසා ගැනීම ගැන හිතන අයට මානසික සහාය."),
    "1333": ("CCCline", "CCC පදනමෙන් නොමිලේ දෙන අර්බුද සහාය සේවය."),
    "119": ("හදිසි ඇමතුම් (පොලිසිය)", "ඔබට හෝ වෙන කෙනෙකුට දැන්ම අනතුරක් තියෙනවා නම්."),
    "1990": ("සුව සැරිය ගිලන් රථ සේවය", "නොමිලේ හදිසි ගිලන් රථ සේවය."),
    "findahelpline.com": ("Find A Helpline", "බොහෝ රටවල නොමිලේ, රහසිගත සහාය අංක."),
}
_HOURS_SI = {"24/7": "පැය 24 පුරා"}


def _localise(r: Resource, lang: str) -> Resource:
    if lang != "si" or r.contact not in _SINHALA:
        return r
    name, description = _SINHALA[r.contact]
    return r.model_copy(
        update={"name": name, "description": description, "hours": _HOURS_SI.get(r.hours, r.hours)}
    )


def resources_for(region: str, lang: str = "en") -> list[Resource]:
    return [_localise(r, lang) for r in (*_BY_REGION.get(region.upper(), []), _INTERNATIONAL)]
