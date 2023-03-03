from opsdroid.matchers import match_regex
from cachetools import TTLCache
from urllib.request import urlopen
import xml.etree.ElementTree as ET
from collections import defaultdict

cache = TTLCache(maxsize=10, ttl=60*60)  # Only retrieve the data every hour


def get_solarxml():
    if "solarxml" not in cache:
        resp = urlopen("https://www.hamqsl.com/solarxml.php")
        root = ET.fromstring(resp.read())
        cache["solarxml"] = root
    return cache["solarxml"]


def get_band_info():
    solar = get_solarxml()[0]

    conditions = solar.find("calculatedconditions")
    bands = defaultdict(dict)
    for band in conditions.iter("band"):
        bands[band.attrib["name"]][band.attrib["time"]] = band.text

    vhfconditions = solar.find("calculatedvhfconditions")
    vhf = defaultdict(dict)
    for band in vhfconditions.iter("phenomenon"):
        bands[band.attrib["name"]][band.attrib["location"]] = band.text

    info = {}
    for tag in solar:
        if tag.tag.startswith("calculated"):
            continue
        info[tag.tag] = tag.text

    band_info = {
        "bands": dict(bands),
        "vhf": dict(vhf),
        "info": info,
    }
    return band_info


@match_regex("^!bands")
async def bands(opsdroid, config, message):
    band_info = get_band_info()
    await message.respond(f"{band_info=}")
