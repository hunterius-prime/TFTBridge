#
# BigTreeTech TFT bridge
#
# Author: K. Hui, Hunterius
#

import logging
import serial
import threading

DEFAULT_TIMEOUT = 1.    # serial read timeout (s), lets threads notice stop requests
RECONNECT_DELAY = 2.    # delay (s) between attempts to (re)open serial ports
STOP_TIMEOUT = 3.       # max time (s) to wait for threads on disconnect

class TftBridge:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        #
        # get config
        #
        self.tftDevice = config.get('tft_device')
        self.tftBaud = config.getint('tft_baud', 250000, minval=1)
        self.tftTimeout = config.getfloat('tft_timeout', DEFAULT_TIMEOUT, minval=0.)
        self.klipperDevice = config.get('klipper_device')
        self.klipperBaud = config.getint('klipper_baud', 250000, minval=1)
        self.klipperTimeout = config.getfloat('klipper_timeout', DEFAULT_TIMEOUT, minval=0.)
        self.machine_extruder_count = config.getint('machine_extruder_count', 1, minval=1)
        self.machine_zprobe = config.getint('machine_zprobe', 0, minval=0, maxval=1)
        self.machine_autolevel = config.getint('machine_autolevel', 0, minval=0, maxval=1)
        self.machine_autoreport_pos = config.getint('machine_autoreport_pos', 0, minval=0, maxval=1)
        self.machine_autoreport_temp = config.getint('machine_autoreport_temp', 0, minval=0, maxval=1)
        #
        # connections to TFT and Klipper serial ports
        #
        self.tftSerial = None
        self.klipperSerial = None
        self.connectLock = threading.Lock()   # guards opening/closing of ports
        self.tftWriteLock = threading.Lock()  # both threads write to TFT
        self.connectFailed = False
        #
        # klipper objects, looked up when printer is ready
        #
        self.gcodeMove = None
        #
        # event and threads for forwarding data
        #
        self.stopEvent = threading.Event()
        self.threads = []
        #
        # register event handlers
        #
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        self.printer.register_event_handler("klippy:disconnect", self.handle_disconnect)

    #
    # open serial port to device
    #
    def openDevice(self, device, baud, timeout):
        if timeout <= 0:
            timeout = DEFAULT_TIMEOUT  # blocking reads would keep threads from stopping
        return serial.Serial(device, baud, timeout=timeout)

    #
    # open serial ports if needed, returns (tftSerial, klipperSerial) or None
    #
    def ensureConnected(self):
        with self.connectLock:
            try:
                if self.tftSerial is None:
                    self.tftSerial = self.openDevice(self.tftDevice, self.tftBaud, self.tftTimeout)
                if self.klipperSerial is None:
                    self.klipperSerial = self.openDevice(self.klipperDevice, self.klipperBaud, self.klipperTimeout)
            except (serial.SerialException, OSError) as e:
                if not self.connectFailed:
                    logging.warning("tftbridge: unable to open serial port: %s", e)
                self.connectFailed = True
                return None
            if self.connectFailed:
                logging.info("tftbridge: serial ports connected")
                self.connectFailed = False
            return self.tftSerial, self.klipperSerial

    #
    # close serial ports, but only if they were not already replaced by another thread
    #
    def closeDevices(self, tftSerial, klipperSerial):
        with self.connectLock:
            if self.tftSerial is not tftSerial or self.klipperSerial is not klipperSerial:
                return
            for serialPort in (tftSerial, klipperSerial):
                if serialPort is not None:
                    try:
                        serialPort.close()
                    except Exception:
                        pass
            self.tftSerial = None
            self.klipperSerial = None

    #
    # read one complete line, returns None on timeout (partial data stays in buffer)
    #
    def readLine(self, serialPort, buffer):
        buffer.extend(serialPort.readline())
        if not buffer.endswith(b'\n'):
            return None
        line = bytes(buffer)
        buffer.clear()
        return line

    #
    # write to TFT, serialized between threads so responses do not interleave
    #
    def writeTft(self, tftSerial, data):
        with self.tftWriteLock:
            tftSerial.write(data)

    #
    # event handler when printer is ready
    #
    def handle_ready(self):
        self.gcodeMove = self.printer.lookup_object('gcode_move')
        #
        # create and start threads, they open the serial ports themselves
        #
        self.stopEvent.clear()
        self.threads = [
            threading.Thread(target=self.tft2klipper, daemon=True),
            threading.Thread(target=self.klipper2tft, daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    #
    # Handle custom commands
    #
    def handle_custom_commands(self, command, tftSerial):
        command = command.upper()

        if command == b'M115':
            response = (
                f"FIRMWARE_NAME:Klipper EXTRUDER_COUNT:{self.machine_extruder_count}\n"
                f"Cap:AUTOLEVEL:{self.machine_autolevel}\n"
                f"Cap:EEPROM:0\n"
                f"Cap:Z_PROBE:{self.machine_zprobe}\n"
                f"Cap:LEVELING_DATA:1\n"
                f"Cap:AUTOREPORT_POS:{self.machine_autoreport_pos}\n"
                f"Cap:AUTOREPORT_TEMP:{self.machine_autoreport_temp}\n"
                f"ok\n"
            )
            self.writeTft(tftSerial, response.encode('utf-8'))
            return True

        #
        # TFT queries speed/flow with bare M220/M221, Klipper would reset them to 100%
        # (get_status only reads plain attributes, safe enough to call from this thread)
        #
        if command in (b'M220', b'M221'):
            status = self.gcodeMove.get_status(self.reactor.monotonic())
            if command == b'M220':
                response = f"FR:{round(status['speed_factor'] * 100.)}%\nok\n"
            else:
                response = f"echo:E0 Flow: {round(status['extrude_factor'] * 100.)}%\nok\n"
            self.writeTft(tftSerial, response.encode('utf-8'))
            return True

        unknown_commands = {
            b'M92': 'M92',
            b'M503': 'M503',
            b'M500': 'M500',
            # Add more commands as needed
        }

        if command in unknown_commands:
            response = f'// Unknown command:"{unknown_commands[command]}"\nok\n'
            self.writeTft(tftSerial, response.encode('utf-8'))
            return True

        return False

    #
    # Translate incoming commands
    #
    def translate_command(self, command):
        #some commands moved to gcode macros of klipper
        command_mapping = {
                    #b'M108': b'CANCEL_PRINT',
                    # Add more commands as needed
        }

        return command_mapping.get(command, command)

    #
    # forward data from TFT to Klipper
    #
    def tft2klipper(self):
        buffer = bytearray()
        while not self.stopEvent.is_set():
            ports = self.ensureConnected()
            if ports is None:
                self.stopEvent.wait(RECONNECT_DELAY)
                continue
            tftSerial, klipperSerial = ports
            try:
                line = self.readLine(tftSerial, buffer)
                if line is None:  # readline timeout
                    continue
                command = line.strip()
                if not command:
                    continue

                # Check for custom commands and respond and not process further
                if self.handle_custom_commands(command, tftSerial):
                    continue

                # Translate the command if needed to klipper format
                klipperSerial.write(self.translate_command(command) + b'\n')
            except Exception:
                if self.stopEvent.is_set():
                    break
                logging.exception("tftbridge: error forwarding TFT -> Klipper")
                self.closeDevices(tftSerial, klipperSerial)
                buffer.clear()
                self.stopEvent.wait(RECONNECT_DELAY)

    #
    # forward data from Klipper to TFT
    #
    def klipper2tft(self):
        buffer = bytearray()
        while not self.stopEvent.is_set():
            ports = self.ensureConnected()
            if ports is None:
                self.stopEvent.wait(RECONNECT_DELAY)
                continue
            tftSerial, klipperSerial = ports
            try:
                line = self.readLine(klipperSerial, buffer)
                if line is not None:  # None on readline timeout
                    self.writeTft(tftSerial, line)
            except Exception:
                if self.stopEvent.is_set():
                    break
                logging.exception("tftbridge: error forwarding Klipper -> TFT")
                self.closeDevices(tftSerial, klipperSerial)
                buffer.clear()
                self.stopEvent.wait(RECONNECT_DELAY)

    #
    # event handler when printer is disconnected
    #
    def handle_disconnect(self):
        self.stopEvent.set()  # signal threads to stop
        #
        # wait for threads, so a restarted instance does not compete for the ports
        #
        for thread in self.threads:
            thread.join(STOP_TIMEOUT)
        self.threads = []
        self.closeDevices(self.tftSerial, self.klipperSerial)

#
# config loading function of add-on
#
def load_config(config):
    return TftBridge(config)
