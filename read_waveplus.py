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

TABLEPRINT_WIDTH = 12
WAVEPLUS_UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"
SCAN_TIMEOUT = 0.1
MAX_SEARCH_COUNT = 50
VALID_SENSOR_VERSION = 1

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
    def __init__(self, serial_number):
        self.periph = None
        self.curr_val_char = None
        self.mac_addr = None
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
        self.sensor_data = [None] * NUMBER_OF_SENSORS
        self.sensor_units = [
            "%rH",
            "Bq/m3",
            "Bq/m3",
            "degC",
            "hPa",
            "ppm",
            "ppb",
        ]

    def set(self, raw_data):
        self.sensor_version = raw_data[0]
        if self.sensor_version != VALID_SENSOR_VERSION:
            print(
                "ERROR: Unknown sensor version.",
                "GUIDE: Contact Airthings for support.",
                sep="\n",
            )
            sys.exit(1)
        self.sensor_data[SENSOR_IDX_HUMIDITY] = raw_data[1] / 2.0
        self.sensor_data[SENSOR_IDX_RADON_SHORT_TERM_AVG] = self.conv2radon(
            raw_data[4]
        )
        self.sensor_data[SENSOR_IDX_RADON_LONG_TERM_AVG] = self.conv2radon(
            raw_data[5]
        )
        self.sensor_data[SENSOR_IDX_TEMPERATURE] = raw_data[6] / 100.0
        self.sensor_data[SENSOR_IDX_REL_ATM_PRESSURE] = raw_data[7] / 50.0
        self.sensor_data[SENSOR_IDX_CO2_LVL] = raw_data[8] * 1.0
        self.sensor_data[SENSOR_IDX_VOC_LVL] = raw_data[9] * 1.0

    def conv2radon(self, radon_raw):
        radon = "N/A"  # Either invalid measurement, or not available
        if 0 <= radon_raw <= 16383:
            radon = radon_raw
        return radon

    def get_value(self, sensor_index):
        return self.sensor_data[sensor_index]

    def get_unit(self, sensor_index):
        return self.sensor_units[sensor_index]


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
        # ---- Initialize ----#
        waveplus = WavePlus(args.serial_number)

        print(f"Device serial number: {args.serial_number}")

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
        else:
            print(tableprint.header(header, width=TABLEPRINT_WIDTH))

        while True:

            waveplus.connect()

            # read values
            sensors = waveplus.read()

            # extract
            humidity = f"{sensors.get_value(SENSOR_IDX_HUMIDITY)} {sensors.get_unit(SENSOR_IDX_HUMIDITY)}"
            radon_st_avg = f"{sensors.get_value(SENSOR_IDX_RADON_SHORT_TERM_AVG)} {sensors.get_unit(SENSOR_IDX_RADON_SHORT_TERM_AVG)}"
            radon_lt_avg = f"{sensors.get_value(SENSOR_IDX_RADON_LONG_TERM_AVG)} {sensors.get_unit(SENSOR_IDX_RADON_LONG_TERM_AVG)}"
            temperature = f"{sensors.get_value(SENSOR_IDX_TEMPERATURE)} {sensors.get_unit(SENSOR_IDX_TEMPERATURE)}"
            pressure = f"{sensors.get_value(SENSOR_IDX_REL_ATM_PRESSURE)} {sensors.get_unit(SENSOR_IDX_REL_ATM_PRESSURE)}"
            co2_lvl = f"{sensors.get_value(SENSOR_IDX_CO2_LVL)} {sensors.get_unit(SENSOR_IDX_CO2_LVL)}"
            voc_lvl = f"{sensors.get_value(SENSOR_IDX_VOC_LVL)} {sensors.get_unit(SENSOR_IDX_VOC_LVL)}"

            # Print data
            data = [
                humidity,
                radon_st_avg,
                radon_lt_avg,
                temperature,
                pressure,
                co2_lvl,
                voc_lvl,
            ]

            if args.pipe:
                print(*data, sep=",")
            else:
                print(tableprint.row(data, width=TABLEPRINT_WIDTH))

            waveplus.disconnect()

            time.sleep(args.sample_period)

    finally:
        waveplus.disconnect()


if __name__ == "__main__":
    main()
