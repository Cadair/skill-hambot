import xml.etree.ElementTree as ET
from collections import defaultdict
from textwrap import dedent
from urllib.request import urlopen
from copy import copy

from cachetools import TTLCache
from opsdroid.connector.matrix import ConnectorMatrix
from opsdroid.connector.matrix.events import GenericMatrixRoomEvent
from opsdroid.events import Message
from opsdroid.matchers import match_regex
from opsdroid.skill import Skill
from tabulate import tabulate

HAMBOT_COMMAND_PREFIX = "!"
HAMBOT_COMMANDS = {}


def regex_command(command, description="", **kwargs):
    """
    A decorator which wraps opsdroid's match_regex to register a command with the !help command.
    """
    HAMBOT_COMMANDS[command] = description
    def decorator(func):
        return match_regex(f"^{HAMBOT_COMMAND_PREFIX}{command}", **kwargs)(func)
    return decorator


@regex_command("help", "print this help message")
async def help(opsdroid, config, message):
    commands = "\n".join([f"{HAMBOT_COMMAND_PREFIX}{command} - {description}" for command, description in HAMBOT_COMMANDS.items()])
    help_text = dedent("""\
    Hambot understands the following commands:

    {commands}
    """).format(commands=commands)
    await message.respond(help_text)


def rich_response(message, body, formatted_body):
    if isinstance(message.connector, ConnectorMatrix):
        return GenericMatrixRoomEvent(
            "m.room.message",
            {
                "body": body,
                "format": "org.matrix.custom.html",
                "formatted_body": formatted_body,
                "msgtype": "m.notice" if message.connector.send_m_notice else "m.text",
            },
        )
    else:
        return Message(body)


class SolarInfo(Skill):
    """
    An opsdroid skill to retrieve propagation information.
    """
    cache = TTLCache(maxsize=10, ttl=60*60)  # Only retrieve the data every hour

    def get_solarxml(self):
        if "solarxml" not in self.cache:
            resp = urlopen("https://www.hamqsl.com/solarxml.php")
            root = ET.fromstring(resp.read())
            self.cache["solarxml"] = root
        return self.cache["solarxml"]

    @property
    def band_info(self):
        solar = self.get_solarxml()[0]

        conditions = solar.find("calculatedconditions")
        bands = defaultdict(dict)
        for band in conditions.iter("band"):
            bands[band.attrib["name"]][band.attrib["time"]] = band.text

        band_table = {"tabular_data": [], "headers": ["Band", "Day", "Night"]}
        for band, conditions in bands.items():
            band_table["tabular_data"].append([band, conditions["day"], conditions["night"]])

        vhfconditions = solar.find("calculatedvhfconditions")
        vhf = defaultdict(dict)
        for band in vhfconditions.iter("phenomenon"):
            vhf[band.attrib["name"]][band.attrib["location"]] = band.text

        info = {}
        for tag in solar:
            if tag.tag.startswith("calculated"):
                continue
            info[tag.tag] = tag.text

        band_info = {
            "bands": band_table,
            "vhf": dict(vhf),
            "info": info,
        }
        return band_info

    @regex_command("bands", "print a propagation prediction for the HF bands.")
    async def bands(self, message):
        band_info = self.band_info["bands"]

        # Colourise the html table
        html_rows = copy(band_info)
        colour = defaultdict(lambda: "")
        colour["Good"] = " data-mx-color='#00cc00'"
        colour["Poor"] = " data-mx-color='#cc0000'"
        colour["Fair"] = " data-mx-color='#ffcc00'"
        new_rows = []
        for row in html_rows["tabular_data"]:
            new_rows.append([f"<font{colour[r]}>{r}</font>" for r in row])
        html_rows["tabular_data"] = new_rows
        html_table = tabulate(**html_rows, tablefmt="unsafehtml")

        # Generate the event class based on the connector type
        event = rich_response(
            message,
            tabulate(**band_info),
            html_table,
        )
        await message.respond(event)

    # @regex_command("vhf", "print a report on VHF propagation effects.")
    # async def vhf(self, message):
    #     band_info = self.band_info
    #     await message.respond(f"{band_info['vhf']}")
