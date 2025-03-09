#APRIL 1 2022 
#Jorge Enrique Gamboa Fuentes
#Subway schedule board - single direction
#Data from: Boston - MBTA
# .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - .l. - 

import time
import microcontroller
from board import NEOPIXEL
import displayio
import adafruit_display_text.label
from adafruit_datetime import datetime
from adafruit_matrixportal.matrix import Matrix
import gc
import json
from adafruit_bitmap_font import bitmap_font

import os
import board
import busio
from digitalio import DigitalInOut
import adafruit_connection_manager
import adafruit_requests
from adafruit_esp32spi import adafruit_esp32spi
import rtc


# Read secrets from settings.toml
WIFI_SSID = os.getenv("WIFI_SSID")
WIFI_PASSWORD = os.getenv("WIFI_PASSWORD")

#CONFIGURABLE PARAMETERS
#-*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*-
BOARD_TITLE = 'Pru'
STOP_ID = 'place-prmnl'
DIRECTION_ID = '1'
ROUTE = 'Green-E'
BACKGROUND_IMAGE_GL = 'TGreen-dashboard.bmp'
BACKGROUND_IMAGE_OL = 'TOrange-dashboard.bmp'
PAGE_LIMIT = '3'
DATA_SOURCE = 'https://api-v3.mbta.com/predictions?filter[stop]=place-prmnl&filter[route_type]=0,1&page[limit]=3'
UPDATE_DELAY = 15
SYNC_TIME_DELAY = 30
MINIMUM_MINUTES_DISPLAY = 9
ERROR_RESET_THRESHOLD = 5
#-*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*--*-/-*-\-*-

# Add this to your constants at the top
DISPLAY_DELAY = 5  # How long to show each station in seconds

# Minimize station data
STATIONS = [
    ('Pru', 'https://api-v3.mbta.com/predictions?filter[stop]=place-prmnl&filter[direction_id]=1&filter[route]=Green-E&page[limit]=2'),
    ('BBY', 'https://api-v3.mbta.com/predictions?filter[stop]=place-bbsta&filter[direction_id]=1&filter[route]=Orange&page[limit]=2')
]

font = bitmap_font.load_font("fonts/6x10.bdf")

# --- Display setup ---
matrix = Matrix()
display = matrix.display


# If you are using a board with pre-defined ESP32 Pins:
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

if "SCK1" in dir(board):
    spi = busio.SPI(board.SCK1, board.MOSI1, board.MISO1)
else:
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

pool = adafruit_connection_manager.get_radio_socketpool(esp)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)
requests = adafruit_requests.Session(pool, ssl_context)

if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    print("ESP32 found and in idle mode")
print("Firmware vers.", esp.firmware_version)
print("MAC addr:", ":".join("%02X" % byte for byte in esp.MAC_address))

for ap in esp.scan_networks():
    print("\t%-23s RSSI: %d" % (ap.ssid, ap.rssi))

print("Connecting to AP...")
while not esp.is_connected:
    try:
        esp.connect_AP(WIFI_SSID, WIFI_PASSWORD)
    except OSError as e:
        print("could not connect to AP, retrying: ", e)
        continue
print("Connected to", esp.ap_info.ssid, "\tRSSI:", esp.ap_info.rssi)




def get_arrival_in_minutes_from_now(now, date_str):
    try:
        train_date = datetime.fromisoformat(date_str)
        # Convert to minutes using individual components
        minutes_diff = (train_date.hour - now.tm_hour) * 60 + (train_date.minute - now.tm_min)
        
        return minutes_diff
    except Exception as e:
        print("Time calculation error:", e)
        return -999

def format_time(time_str):
    try:
        # Convert the time string to a datetime object first
        time_obj = datetime.fromisoformat(time_str)
        # Format time as "HH:MM" using datetime object
        hour = time_obj.hour
        minute = time_obj.minute
        
        # Convert 24-hour to 12-hour format
        if hour > 12:
            hour -= 12
        elif hour == 0:
            hour = 12
        
        # Format with leading zeros
        return f"{hour:02d}:{minute:02d}"
    except:
        return "--:--"

def setup_display():
    matrix = Matrix()
    display = matrix.display
    
    # Create minimal group
    group = displayio.Group()
    
    # Load the font
    font = bitmap_font.load_font("fonts/6x10.bdf")
    
    # Create text labels with bitmap font
    text_lines = []
    text_lines.append(adafruit_display_text.label.Label(font, color=0x444444, x=2, y=3))   # Station
    text_lines.append(adafruit_display_text.label.Label(font, color=0x444444, x=2, y=11))  # Time
    text_lines.append(adafruit_display_text.label.Label(font, color=0xDD8000, x=26, y=19)) # Train 1
    text_lines.append(adafruit_display_text.label.Label(font, color=0xDD8000, x=26, y=27)) # Train 2
    
    # Add to group
    for line in text_lines:
        group.append(line)
    
    display.root_group = group
    return display, text_lines

# Initialize display once
display, text_lines = setup_display()

def update_text(station_name, current_time, t1, t2):
    # Update background image based on station
    if station_name == 'Pru':
        bitmap = displayio.OnDiskBitmap(open(BACKGROUND_IMAGE_GL, 'rb'))
    else:  # BBY
        bitmap = displayio.OnDiskBitmap(open(BACKGROUND_IMAGE_OL, 'rb'))
    
    # Update the background in the tile grid
    tile_grid = displayio.TileGrid(bitmap, pixel_shader=getattr(bitmap, 'pixel_shader', displayio.ColorConverter()))
    
    # Remove old background and add new one
    while len(group) > len(text_lines):  # Remove old background
        group.pop(0)
    group.insert(0, tile_grid)  # Add new background at position 0
    
    hour = current_time.tm_hour
    minute = current_time.tm_min
        
    # Convert 24-hour to 12-hour format
    if hour > 12:
        hour -= 12
    elif hour == 0:
        hour = 12
        

    # Update text
    text_lines[0].text = station_name        # Station name
    text_lines[1].text = f"{hour:02d}:{minute:02d}"  # Time
    text_lines[2].text = str(text_formating(t1))
    text_lines[3].text = str(text_formating(t2))
    
    display.root_group = group

# Simplify text formatting
def text_formating(trainMinutes):
    try:
        # Convert to integer before comparison
        minutes = int(trainMinutes)
        if minutes == 1:
            return " Arr"
        elif minutes <= 0:
            return " Brd"
        return f"{minutes:2d} min"
    except:
        print("Error formatting time:", trainMinutes)
        return "-----"

def get_arrival_times(station_name, station_url):
    print("Getting arrival times")
    now = time.localtime()
    
    # Default values
    train1_min = -999
    train2_min = -888
    
    try:
        stop_trains = requests.get(station_url)
        res = stop_trains.json()
        
        if "data" in res and len(res["data"]) > 0:
            try:
                train1 = res["data"][0]["attributes"]["arrival_time"]
                train1_min = get_arrival_in_minutes_from_now(now, train1)
            except (KeyError, IndexError, ValueError):
                pass
            
            # Add second train
            if len(res["data"]) > 1:
                try:
                    train2 = res["data"][1]["attributes"]["arrival_time"]
                    train2_min = get_arrival_in_minutes_from_now(now, train2)
                except (KeyError, IndexError, ValueError):
                    pass
            
    except Exception as e:
        print("Error fetching data:", e)
        print("Error type:", type(e).__name__)

    # Call update_text directly with the calculated minutes
    update_text(station_name, now, train1_min, train2_min)


# --- Drawing setup ---
group = displayio.Group()
bitmap = displayio.OnDiskBitmap(open(BACKGROUND_IMAGE_OL, 'rb'))
colors = [0x444444, 0xDD8000]  # [dim white, gold]

# Create the background first
tile_grid = displayio.TileGrid(bitmap, pixel_shader=getattr(bitmap, 'pixel_shader', displayio.ColorConverter()))
group.append(tile_grid)

# Create text labels separately
text_lines = []
text_lines.append(adafruit_display_text.label.Label(font, color=colors[0], x=26, y=3, text="Station"))   # Station name
text_lines.append(adafruit_display_text.label.Label(font, color=colors[0], x=26, y=11, text="Time"))     # Current time
text_lines.append(adafruit_display_text.label.Label(font, color=colors[1], x=26, y=19, text="- min"))   # Train 1
text_lines.append(adafruit_display_text.label.Label(font, color=colors[1], x=26, y=27, text="- min"))   # Train 2

# Add all text labels to the group
for line in text_lines:
    group.append(line)

# Set the display's root group
display.root_group = group

error_count = 0


station_index = 0

TIME_API = "http://worldtimeapi.org/api/ip"
the_rtc = rtc.RTC()

response = None
while True:
    try:
        print("Fetching json from", TIME_API)
        response = requests.get(TIME_API)
        break
    except OSError as e:
        print("Failed to get data, retrying\n", e)
        continue

json = response.json()
current_time = json["datetime"]
the_date, the_time = current_time.split("T")
year, month, mday = [int(x) for x in the_date.split("-")]
the_time = the_time.split(".")[0]
hours, minutes, seconds = [int(x) for x in the_time.split(":")]

# We can also fill in these extra nice things
year_day = json["day_of_year"]
week_day = json["day_of_week"]
is_dst = json["dst"]

now = time.struct_time(
    (year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst)
)
print(now)
the_rtc.datetime = now

# Main loop using pre-allocated variables
while True:

    try:
        get_arrival_times(STATIONS[station_index][0], STATIONS[station_index][1])
        
    except Exception as e:
        print("\nError in main loop:", e)
        print("Error type:", type(e).__name__)
        error_count += 1
        if error_count > ERROR_RESET_THRESHOLD:
            microcontroller.reset()
    
    gc.collect()
    time.sleep(UPDATE_DELAY)
    station_index = (station_index + 1) % len(STATIONS)
