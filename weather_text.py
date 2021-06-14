import json
import requests
from enum import Enum
from statistics import mean
import sys
import math
import datetime

global user
global password 
global coords
data_params = "air_temperature,cloud_area_fraction,lwe_precipitation_rate,wind_from_direction,wind_speed"
request_path = "https://wod.belgingur.is/api/v2/data/point/schedule/island-8-2/2/latlon/{latlon}/vars/{data_params}.json"

global lang 
lang = 1

class Lang(Enum):
    IS = 0
    EN = 1
    ES = 2

class Template(Enum):
    TEMP = 0
    WIND_SLOW = 1
    WIND_STD = 2
    CLOUDS_CLEAR = 3
    CLOUDS_HALF = 4
    CLOUDS_FULL = 5
    MORNING = 6
    AFTERNOON = 7
    WIND_VARIABLE = 8
    NIGHT = 9
    RAIN_LITTLE = 10
    CLOUDS_CLOUDY = 11
    RAIN_MODERATE = 12
    RAIN_HEAVY = 13
    EVENING = 14
    WIND_NONE = 15

templates =  [["Hiti {min} - {max} gráður.",        "Hæg breytileg átt.",  "{dir} {min} - {max} m/s.", "Heiðskýrt.",   "Hálfskýjað.",  "Alskýjað.", "Morgunn:", "Seinni partur:", "Breytilegir vindar.", "Aðra nótt:",      "Lítilsháttar rigning.", "Skýjað", "Rigning.", "Töluverð rigning.", "Kvöld:",   "Logn."],
             ["Temperature {min} - {max} degrees.", "Calm winds.",         "{dir} {min} - {max} m/s.", "Clear skies.", "Some clouds.", "Cloudy",    "Morning:", "Afternoon:",     "Changable winds.",    "Tomorrow night:", "Light rain.",           "Cloudy", "Rain",     "Heavy rain",        "Evening:", "Calm."],
             ["Temperatura {min} - {max} grados.",  "Vientos tranquilos.", "{dir} {min} - {max} m/s.", "",             "",             "",          "",              "",              "",                    "",                ""]]

directions = [["N","NNA","NA","ANA","A","ASA", "SA", "SSA","S","SSV","SV","VSV","V","VNV","NV","NNV"], 
             ["N","NNE","NE","ENE","E","ESE", "SE", "SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"], 
             ["N","NNE","NE","ENE","E","ESE", "SE", "SSE","S","SSO","SO","OSO","O","ONO","NO","NNO"]]


# Find the index of the first data point for the next day.
def find_starting_point(times):
    tomorrow = datetime.date.today() + datetime.timedelta(days=1) 
    day = tomorrow.strftime("%d")
    for t in range(25):
        if times[t][8:10] == day:
            return t


def get_weather_data():
    response = requests.get(request_path.format(latlon=coords, data_params=data_params), auth=(user, password))
    data = json.loads(response.text)

    # The API returns a seemingly arbitrary number of points from the current day, so we find the start of the next day and take data from there.
    times = data["time"]
    data_start = find_starting_point(times)

    # Take only the next day of data and the first 4 hours of the next day
    temp = data["data"]["air_temperature"][data_start:data_start+30]
    wind_dir = data["data"]["wind_from_direction"][data_start:data_start+30]
    wind_sp = data["data"]["wind_speed"][data_start:data_start+30]
    clouds = data["data"]["cloud_area_fraction"][data_start:data_start+30]
    rain = data["data"]["lwe_precipitation_rate"][data_start:data_start+30]
    return temp, wind_dir, wind_sp, clouds, rain


def deg_to_comp(deg):
    val = int(((deg%360)/22.5)+.5)
    return directions[lang][val]


# Switches between the clockwise, 0 at top compass system and the counter-clockwise 
# 0 to the right coordinate system. Works both ways.
def coord_system_switch(ang):
    return 360-((ang-90)%360)%360


def avg_wind_dir(wind_dir):
    conv_wind_dir = [coord_system_switch(a) for a in wind_dir]
    si = mean([math.sin(dir*math.pi/180) for dir in conv_wind_dir])
    co = mean([math.cos(dir*math.pi/180) for dir in conv_wind_dir])

    # To avoid a div by 0, add a fraction to a value and calculate again. 
    if co == 0:
        conv_wind_dir[0] += 0.000001
        si = mean([math.sin(dir*math.pi/180) for dir in conv_wind_dir])
        co = mean([math.cos(dir*math.pi/180) for dir in conv_wind_dir])

    if co < 0:
        return coord_system_switch(math.atan(si/co)*(180/math.pi)+180)
    else:
        if si > 0:
            return coord_system_switch(math.atan(si/co)*(180/math.pi))
        else:
            return coord_system_switch(math.atan(si/co)*(180/math.pi)+360)


def wind_change(wind_dir):
    total_change = 0
    for dir in range(len(wind_dir)-1):
        change = wind_dir[dir]-wind_dir[dir+1]
        if change > 180:
            change = 360-change
        total_change += change
    return total_change


def gen_temp(temp):
    return Template.TEMP.value, round(min(temp)), round(max(temp))


def gen_wind(wind_dir, wind_sp):
    if max(wind_sp) == 0:
        return Template.WIND_NONE.value, 0, 0, 0

    if max(wind_sp) < 2:
        return Template.WIND_SLOW.value, 0, 0, 0

    if wind_change(wind_dir) < 180:
        dir = avg_wind_dir(wind_dir)
        sp_low = round(min(wind_sp))
        sp_high = round(max(wind_sp))
        return Template.WIND_STD.value, deg_to_comp(dir), sp_low, sp_high

    return Template.WIND_VARIABLE.value, 0, 0, 0
    

def gen_clouds(clouds, rain):
    if mean(rain) < 0.2 and mean(rain) > 0:
        return Template.RAIN_LITTLE.value
    elif mean(rain) < 1 and mean(rain) > 0:
        return Template.RAIN_MODERATE.value
    elif mean(rain) > 0:
        return Template.RAIN_HEAVY.value

    if mean(clouds) < 0.25:
        return Template.CLOUDS_CLEAR.value
    elif mean(clouds) < 0.75:
        return Template.CLOUDS_HALF.value
    elif mean(clouds) < 0.9:
        return Template.CLOUDS_CLOUDY.value
    else:
        return Template.CLOUDS_FULL.value


def gen_time_interval(temp, wind_dir, wind_sp, clouds, rain):
    forecast = ""

    # Wind
    wind_template, wind_1, wind_2, wind_3 = gen_wind(wind_dir, wind_sp)
    forecast += templates[lang][wind_template].format(dir=wind_1, min=wind_2, max=wind_3)
    forecast += " "

    # Clouds/precipitation
    cloud_template = gen_clouds(clouds, rain)
    forecast += templates[lang][cloud_template]
    forecast += " "

    # Temperature
    temp_template, temp_min, temp_max = gen_temp(temp)
    forecast += templates[lang][temp_template].format(min=temp_min, max=temp_max)

    return forecast


def gen_text_forecast():
    forecast = ""

    # Get weather data
    temp, wind_dir, wind_sp, clouds, rain = get_weather_data()

    # Genertate morning forecast
    forecast += templates[lang][Template.MORNING.value]
    forecast += "\n"
    forecast += gen_time_interval(temp[6:12], wind_dir[6:12], wind_sp[6:12], clouds[6:12], rain[6:12])

    # Generate afternoon forecast
    forecast += "\n"
    forecast += templates[lang][Template.AFTERNOON.value]
    forecast += "\n"
    forecast += gen_time_interval(temp[12:18], wind_dir[12:18], wind_sp[12:18], clouds[12:18], rain[12:18])

    # Generate evening forecast
    forecast += "\n"
    forecast += templates[lang][Template.EVENING.value]
    forecast += "\n"
    forecast += gen_time_interval(temp[18:24], wind_dir[18:24], wind_sp[18:24], clouds[18:24], rain[18:24])

    # Generate night forecast
    forecast += "\n"
    forecast += templates[lang][Template.NIGHT.value]
    forecast += "\n"
    forecast += gen_time_interval(temp[24:30], wind_dir[24:30], wind_sp[24:30], clouds[24:30], rain[24:30])

    return forecast


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise ValueError("Too few arguments.\nUsage: python3 weather_text.py lat, lon, lang, user, pass")
    
    if len(sys.argv) > 6:
        raise ValueError("Too many arguments.\nUsage: python3 weather_text.py lat, lon, lang, user, pass")

    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    set_lang = sys.argv[3].upper()
    
    try:
        if lat >=-180 and lat <=180 and lon >= -90 and lon <= 90:
            coords = "{lat},{lon}".format(lat=lat, lon=lon)
        else:
             raise ValueError("Invalid coordinates")
    except:
        raise ValueError("Invalid coordinates")
    
    try:
        if set_lang in Lang._member_names_:
            lang = Lang[set_lang].value
        else:
            raise ValueError("Invalid language")
    except:
        raise ValueError("Invalid language")

    if len(sys.argv) == 6:
        user = sys.argv[4]
        password = sys.argv[5]

    print(gen_text_forecast())
    