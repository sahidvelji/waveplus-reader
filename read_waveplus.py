# MIT License
#
# Copyright (c) 2018 Airthings AS
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# https://airthings.com

# ===============================
# Module import dependencies
# ===============================

from bluepy.btle import UUID, Peripheral, Scanner, DefaultDelegate
import sys
import time
import struct
import tableprint
import argparse

# ===============================
# Global variables
# ===============================

NUMBER_OF_SENSORS = 7
SENSOR_IDX_HUMIDITY = 0
SENSOR_IDX_RADON_SHORT_TERM_AVG = 1
SENSOR_IDX_RADON_LONG_TERM_AVG = 2
SENSOR_IDX_TEMPERATURE = 3
SENSOR_IDX_REL_ATM_PRESSURE = 4
SENSOR_IDX_CO2_LVL = 5
SENSOR_IDX_VOC_LVL = 6

VARIABLES = [
    "humidity",
    "radon_sta",
    "radon_lta",
    "temperature",
    "pressure",
    "co2",
    "voc",
]

TABLEPRINT_WIDTH = 12
WAVEPLUS_UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"
SCAN_TIMEOUT = 0.1
MAX_SEARCH_COUNT = 50
VALID_SENSOR_VERSION = 1

# ====================================
# Variable classes
# ====================================


class Humidity(float):
    def __new__(cls, value):
        return super(Humidity, cls).__new__(cls, value)

    def __init__(self, value):
        self.value = value
        self.unit = "%rH"
        self.status = self.status()

    def __str__(self):
        return f"{super().__str__()} {self.unit}"

    def status(self):
        if self < 25 or self >= 70:
            return "red"
        if 60 <= self < 70 or 25 <= self < 30:
            return "yellow"
        return "green"


class Radon(int):
    def __new__(cls, value):
        return super(Radon, cls).__new__(cls, value)

    def __init__(self, value):
        self.value = value
        self.unit = "Bq/m3"
        self.status = self.status()

    def __str__(self):
        return f"{super().__str__()} {self.unit}"

    def status(self):
        if self >= 150:
            return "red"
        if self >= 100:
            return "yellow"
        return "green"


class Temperature(float):
    def __new__(cls, value):
        return super(Temperature, cls).__new__(cls, value)

    def __init__(self, value):
        self.value = value
        self.unit = "degC"
        self.status = self.status()

    def __str__(self):
        return f"{super().__str__()} {self.unit}"

    def status(self):
        if self >= 25:
            return "red"
        if self < 18:
            return "blue"
        return "green"


class Pressure(int):
    def __new__(cls, value):
        return super(Pressure, cls).__new__(cls, value)

    def __init__(self, value):
        self.value = value
        self.unit = "hPa"
        self.status = "N/A"

    def __str__(self):
        return f"{super().__str__()} {self.unit}"


class CO2(int):
    def __new__(cls, value):
        return super(CO2, cls).__new__(cls, value)

    def __init__(self, value):
        self.value = value
        self.unit = "ppm"
        self.status = self.status()

    def __str__(self):
        return f"{super().__str__()} {self.unit}"

    def status(self):
        if self >= 1000:
            return "red"
        if self >= 800:
            return "yellow"
        return "green"


class VOC(int):
    def __new__(cls, value):
        return super(VOC, cls).__new__(cls, value)

    def __init__(self, value):
        self.value = value
        self.unit = "ppb"
        self.status = self.status()

    def __str__(self):
        return f"{super().__str__()} {self.unit}"

    def status(self):
        if self >= 2000:
            return "red"
        if self >= 250:
            return "yellow"
        return "green"


# ====================================
# Utility functions for WavePlus class
# ====================================


def parse_serial_number(manu_data_hex_str):
    if manu_data_hex_str is None or manu_data_hex_str == "None":
        sn = "Unknown"
    else:
        manu_data = bytearray.fromhex(manu_data_hex_str)

        if ((manu_data[1] << 8) | manu_data[0]) == 0x0334:
            sn = manu_data[2]
            sn |= manu_data[3] << 8
            sn |= manu_data[4] << 16
            sn |= manu_data[5] << 24
        else:
            sn = "Unknown"
    return sn


# ===============================
# Class WavePlus
# ===============================


class WavePlus:
    def __init__(self, serial_number, mac_addr):
        self.periph = None
        self.curr_val_char = None
        self.mac_addr = mac_addr
        self.sn = serial_number
        self.uuid = UUID(WAVEPLUS_UUID)

    def search(self):
        # Auto-discover device on first connection
        scanner = Scanner().withDelegate(DefaultDelegate())
        search_count = 0
        while search_count < MAX_SEARCH_COUNT:
            devices = scanner.scan(SCAN_TIMEOUT)
            search_count += 1
            for dev in devices:
                manu_data = dev.getValueText(255)
                sn = parse_serial_number(manu_data)
                if sn == self.sn:
                    return dev.addr

        # Device not found after MAX_SEARCH_COUNT
        print(
            "ERROR: Could not find device.",
            "GUIDE: (1) Please verify the serial number.",
            "       (2) Ensure that the device is advertising.",
            "       (3) Retry connection.",
            sep="\n",
        )
        sys.exit(1)

    def connect(self):
        if self.mac_addr is None:
            self.mac_addr = self.search()
        if self.periph is None:
            self.periph = Peripheral(self.mac_addr)
        if self.curr_val_char is None:
            self.curr_val_char = self.periph.getCharacteristics(
                uuid=self.uuid
            )[0]

    def read(self):
        if self.curr_val_char is None:
            print("ERROR: Devices are not connected.")
            sys.exit(1)
        raw_data = self.curr_val_char.read()
        raw_data = struct.unpack("<BBBBHHHHHHHH", raw_data)
        sensors = Sensors()
        sensors.set(raw_data)
        return sensors

    def disconnect(self):
        if self.periph is not None:
            self.periph.disconnect()
            self.periph = None
            self.curr_val_char = None


# ===================================
# Class Sensor and sensor definitions
# ===================================


class Sensors:
    def __init__(self):
        self.sensor_version = None
        self.sensor_data = {}

    def set(self, raw_data):
        self.sensor_version = raw_data[0]
        if self.sensor_version != VALID_SENSOR_VERSION:
            print(
                "ERROR: Unknown sensor version.",
                "GUIDE: Contact Airthings for support.",
                sep="\n",
            )
            sys.exit(1)
        self.sensor_data["humidity"] = Humidity(raw_data[1] / 2.0)
        self.sensor_data["radon_sta"] = Radon(self.conv2radon(raw_data[4]))
        self.sensor_data["radon_lta"] = Radon(self.conv2radon(raw_data[5]))
        self.sensor_data["temperature"] = Temperature(raw_data[6] / 100.0)
        self.sensor_data["pressure"] = Pressure(raw_data[7] / 50.0)
        self.sensor_data["co2"] = CO2(raw_data[8] * 1.0)
        self.sensor_data["voc"] = VOC(raw_data[9] * 1.0)

    def conv2radon(self, radon_raw):
        radon = "N/A"  # Either invalid measurement, or not available
        if 0 <= radon_raw <= 16383:
            radon = radon_raw
        return radon

    def get_variable(self, variable):
        return self.sensor_data[variable]


def statusbar_print(data):
    overall_status = "green"
    status = [
        data[var].status
        for var in data
        if var in {"humidity", "co2", "voc", "radon"}
    ]
    print_vars = []
    if "red" in status:
        overall_status = "red"
    elif "yellow" in status:
        overall_status = "yellow"
    for var in data:
        if data[var].status in {"blue", "yellow", "red"}:
            print_vars.append(data[var])
    print(overall_status_emoji(overall_status), end="")
    print(*print_vars, sep=" ")


def overall_status_emoji(status):
    if status == "green":
        return "🟢"
    if status == "yellow":
        return "🟡"
    if status == "red":
        return "🔴"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "serial_number",
        type=int,
        help="the 10-digit serial number found under the magnetic backplate of your Wave Plus",
    )
    parser.add_argument(
        "--sample-period",
        type=int,
        default=300,
        help="the number of seconds between reading the current values. Default: %(default)s",
    )
    parser.add_argument(
        "--pipe", action="store_true", help="pipe the results to a file"
    )
    parser.add_argument(
        "--statusbar",
        action="store_true",
        help="print air quality status suitable for statusbar",
    )
    parser.add_argument(
        "--mac-addr",
        help="the MAC address of the Wave Plus device",
    )
    args = parser.parse_args()

    if len(str(args.serial_number)) != 10:
        print("ERROR: Invalid SN format.")
        parser.print_usage()
        sys.exit(1)

    if args.sample_period <= 0:
        print("ERROR: Invalid SAMPLE-PERIOD. Must be larger than zero.")
        parser.print_usage()
        sys.exit(1)

    try:
        waveplus = WavePlus(args.serial_number, args.mac_addr)

        header = [
            "Humidity",
            "Radon ST avg",
            "Radon LT avg",
            "Temperature",
            "Pressure",
            "CO2 level",
            "VOC level",
        ]

        if args.pipe:
            print(*header, sep=",")
        elif not args.statusbar:
            print(tableprint.header(header, width=TABLEPRINT_WIDTH))

        while True:
            waveplus.connect()
            sensors = waveplus.read()

            data = {var: sensors.get_variable(var) for var in VARIABLES}
            if args.statusbar:
                statusbar_print(data)
                sys.exit(0)

            if args.pipe:
                print(*data.values(), sep=",")
            else:
                print(
                    tableprint.row(
                        list(map(str, data.values())), width=TABLEPRINT_WIDTH
                    )
                )

            waveplus.disconnect()

            time.sleep(args.sample_period)

    finally:
        waveplus.disconnect()


if __name__ == "__main__":
    main()
