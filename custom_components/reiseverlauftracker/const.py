"""Constants for reiseverlauftracker."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "reiseverlauftracker"

CONF_ALTITUDE_ENTITY = "altitude_entity"
CONF_DPLUS_ENTITY = "dplus_entity"
CONF_DPLUS_ON_VALUE = "dplus_on_value"
CONF_OUTPUT_DIR = "output_dir"
CONF_SPEED_ENTITY = "speed_entity"
CONF_TRACKER_ENTITY = "tracker_entity"

SECTION_DETECTION = "detection"
SECTION_EXPORT = "export"
SECTION_THRESHOLDS = "thresholds"
SECTION_LOGBOOK = "logbook"

CONF_ELEVATION_HYSTERESIS = "elevation_hysteresis"
CONF_END_DELAY = "end_delay"
CONF_MARGIN = "margin"
CONF_MAX_ACCURACY = "max_accuracy"
CONF_MERGE_WINDOW = "merge_window"
CONF_MIN_MOVEMENT = "min_movement"
CONF_MIN_POINT_DISTANCE = "min_point_distance"
CONF_MIN_STOP_DURATION = "min_stop_duration"
CONF_PLACE_NAMES = "place_names"
CONF_TANK_SIZE = "tank_size"
CONF_TOLL_COUNTRIES = "toll_countries"
CONF_SCALE = "scale"
CONF_STANDSTILL_SPEED = "standstill_speed"
CONF_TITLE_FORMAT = "title_format"

TITLE_FORMAT_DATE = "date"
TITLE_FORMAT_DATE_PLACE = "date_place"
TITLE_FORMAT_PLACE = "place"
TITLE_FORMATS = [TITLE_FORMAT_DATE_PLACE, TITLE_FORMAT_DATE, TITLE_FORMAT_PLACE]

DEFAULT_DPLUS_ON_VALUE = "on"
DEFAULT_ELEVATION_HYSTERESIS_M = 5.0
DEFAULT_END_DELAY_MIN = 60
DEFAULT_MARGIN_MIN = 10
DEFAULT_MAX_ACCURACY_M = 50.0
DEFAULT_MERGE_WINDOW_H = 6.0
DEFAULT_MIN_MOVEMENT_M = 100.0
DEFAULT_MIN_POINT_DISTANCE_M = 15.0
DEFAULT_MIN_STOP_DURATION_MIN = 5
DEFAULT_OUTPUT_DIR = "reiseverlauf"
DEFAULT_PLACE_NAMES = True
DEFAULT_SCALE = 1.0
DEFAULT_STANDSTILL_SPEED_KMH = 3.0
DEFAULT_TANK_LITRES = 90.0
DEFAULT_TITLE_FORMAT = TITLE_FORMAT_DATE_PLACE

# Countries offered for travel costs and toll settings, as ISO 3166-1 alpha-2 codes; the UI translates them.
COUNTRIES = (
    "AD", "AL", "AT", "BA", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GR", "HR",
    "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MA", "MC", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO",
    "RS", "SE", "SI", "SK", "SM", "TR",
)  # fmt: skip
# Distance-based toll or a toll for motorhomes over 3.5 t (docs/features/feat-09-nachtraege.md 6.5); not DE,
# where motorhomes are exempt from the truck toll.
# Trips this recent count for the open toll sensor; their countries are looked up at start.
OPEN_TOLL_PERIOD = timedelta(days=365)
DEFAULT_TOLL_COUNTRIES = ("AT", "BE", "CH", "CZ", "ES", "FR", "HR", "HU", "IT", "NO", "PL", "PT", "SI", "SK")

EVENT_TRIP_ENDED = f"{DOMAIN}_beendet"
EVENT_TRIP_EXPORTED = f"{DOMAIN}_exportiert"
EVENT_LOGBOOK = f"{DOMAIN}_fahrtenbuch"
EVENT_TRIP_STARTED = f"{DOMAIN}_gestartet"
EVENT_TOUR = f"{DOMAIN}_tour"

EXPORT_CHOICE_ALL = "all"
# Fixed options of the logbook time selection; the stops in between are labelled with their time and place.
LATE_CHOICE_CURRENT = "current"
LATE_CHOICE_OTHER = "other"
# First option of the entry selections: no stored entry chosen, the form adds a new one.
EDIT_CHOICE_NEW = "new"
# Resting option of the selection that clears a logbook form field.
CLEAR_CHOICE_NONE = "none"
