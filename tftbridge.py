#
# BigTreeTech TFT bridge
#
# Author: K. Hui, Hunterius
#

import serial
import threading

class TftBridge:
    def __init__(self, config):
        self.printer = config.get_printer()
        #
        # get config
        #
        self.tftDevice = config.get('tft_device')
        self.tftBaud = config.getint('tft_baud')
        self.tftTimeout = config.getint('tft_timeout')
        self.klipperDevice = config.get('klipper_device')
        self.klipperBaud = config.getint('klipper_baud')
        self.klipperTimeout = config.getint('klipper_timeout')
        self.machine_extruder_count = config.getint('machine_extruder_count')
        self.machine_zprobe = config.getint('machine_zprobe')
        self.machine_autoreport_pos = config.getint('machine_autoreport_pos')
        self.machine_autoreport_temp = config.getint('machine_autoreport_temp')
        self.machine_autolevel = config.getint('machine_autolevel')
        #
        # connections to TFT and Klipper serial ports
        #
        self.tftSerial = None
        self.klipperSerial = None
        #
        # event to signal stopping threads
        #
        self.stopEvent = threading.Event()
        #
        # register event handlers
        #
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        self.printer.register_event_handler("klippy:disconnect", self.handle_disconnect)

    #
    # open serial port to device
    #
    def openDevice(self, device, baud, timeout):
        if timeout == 0:
            serialPort = serial.Serial(device, baud)
        else:
            serialPort = serial.Serial(device, baud, timeout=timeout)
        return serialPort

    #
    # event handler when printer is ready
    #
    def handle_ready(self):
        #
        # create connections to devices if needed
        #
        if self.tftSerial is None:
            try:
                self.tftSerial = self.openDevice(self.tftDevice, self.tftBaud, self.tftTimeout)
            except:
                self.tftSerial = None

        if self.klipperSerial is None:
            try:
                self.klipperSerial = self.openDevice(self.klipperDevice, self.klipperBaud, self.klipperTimeout)
            except:
                self.klipperSerial = None
        #
        # create and start threads
        #
        self.stopEvent.clear()
        threading.Thread(target=self.tft2klipper).start()
        threading.Thread(target=self.klipper2tft).start()

    #
    # Handle custom commands
    #
    def handle_custom_commands(self, line):
        if line == b'M115\n':
            response = (
                f"FIRMWARE_NAME:Klipper EXTRUDER_COUNT:{self.machine_extruder_count}\n"
                f"Cap:AUTOLEVEL:{self.machine_autolevel}\n"
                f"Cap:EEPROM:0\n"
                f"Cap:Z_PROBE:{self.machine_zprobe}\n"
                f"Cap:LEVELING_DATA:1\n"
                f"Cap:AUTOREPORT_POS:{self.machine_autoreport_pos}\n"
                f"Cap:AUTOREPORT_TEMP:{self.machine_autoreport_temp}\n"
            )

            self.tftSerial.write(response.encode('utf-8'))
            self.tftSerial.write(b'ok\n')
            return True

        unknown_commands = {
            b'M92\n': 'M92',
            b'M503\n': 'M503',
            b'M500\n': 'M500',
            # Add more commands as needed
        }

        if line in unknown_commands:
            command = unknown_commands[line]
            response = f'// Unknown command:"{command}"\n'
            self.tftSerial.write(response.encode('utf-8'))
            self.tftSerial.write(b'ok\n')
            return True

        return False

    #
    # Translate incoming commands
    #
    def translate_command(self, line):
        command_mapping = {
            b'G34\n': b'Z_TILT_ADJUST\n',
            b'M108\n': b'CANCEL_PRINT\n',
            # Add more commands as needed
        }

        return command_mapping.get(line, line)

    #
    # forward data from TFT to Klipper
    #
    def tft2klipper(self):
        while True:
            #
            # if stopping thread event is set
            #
            if self.stopEvent.is_set():
                if self.tftSerial is not None:
                    self.tftSerial.close()  # close connection to TFT
                self.tftSerial = None  # clear property
                break
            #
            # otherwise read from TFT and forward to Klipper
            #
            if self.tftSerial is not None and self.klipperSerial is not None:
                try:
                    line = self.tftSerial.readline()
                    if line != '':  # if readline timeout, it returns an empty str

                        # Check for custom commands and respond and not process further
                        if self.handle_custom_commands(line):
                            continue

                        # Translate the command if needed to klipper format
                        line = self.translate_command(line)

                        self.klipperSerial.write(line)
                except:
                    pass

    #
    # forward data from Klipper to TFT
    #
    def klipper2tft(self):
        while True:
            #
            # if stopping thread event is set
            #
            if self.stopEvent.is_set():
                if self.klipperSerial is not None:
                    self.klipperSerial.close()  # close connection to Klipper
                self.klipperSerial = None  # clear property
                break
            #
            # otherwise read from Klipper and forward to TFT
            #
            if self.tftSerial is not None and self.klipperSerial is not None:
                try:
                    line = self.klipperSerial.readline()
                    if line != '':  # if readline timeout, it returns an empty str
                        self.tftSerial.write(line)
                except:
                    pass

    #
    # event handler when printer is disconnected
    #
    def handle_disconnect(self):
        self.stopEvent.set()  # signal threads to stop

#
# config loading function of add-on
#
def load_config(config):
    return TftBridge(config)
