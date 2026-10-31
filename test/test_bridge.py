#
# Unit tests for tftbridge.py, run without Klipper or serial hardware:
#   python -m unittest discover test
#

import os
import queue
import sys
import threading
import time
import types
import unittest
from unittest import mock

#
# fake pyserial, each device is a pair of input queue (data the bridge reads) and output list
#
class FakeSerialException(Exception):
    pass

class FakePort:
    devices = {}

    def __init__(self, device, baud, timeout=None):
        if device not in FakePort.devices:
            raise FakeSerialException(f"no such device {device}")
        self.timeout = timeout
        self.closed = False
        self.input, self.output = FakePort.devices[device]

    def readline(self):
        if self.closed:
            raise FakeSerialException("port closed")
        try:
            return self.input.get(timeout=self.timeout)
        except queue.Empty:
            return b''

    def write(self, data):
        if self.closed:
            raise FakeSerialException("port closed")
        self.output.append(data)

    def close(self):
        self.closed = True

fakeSerial = types.SimpleNamespace(Serial=FakePort, SerialException=FakeSerialException)

try:
    import serial  # noqa: F401
except ImportError:
    sys.modules['serial'] = fakeSerial

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import tftbridge

#
# fake Klipper objects
#
class FakeConfig:
    def __init__(self, printer, values):
        self.printer = printer
        self.values = values
        self.accessed = set()

    def get_printer(self):
        return self.printer

    def _get(self, option, default, convert):
        self.accessed.add(option)
        if option in self.values:
            return convert(self.values[option])
        if default is None:
            raise KeyError(f"option '{option}' is required")
        return default

    def get(self, option, default=None):
        return self._get(option, default, str)

    def getint(self, option, default=None, minval=None, maxval=None):
        return self._get(option, default, int)

    def getfloat(self, option, default=None, minval=None, maxval=None):
        return self._get(option, default, float)

class FakeGcodeMove:
    def __init__(self):
        self.speed_factor = 1.
        self.extrude_factor = 1.

    def get_status(self, eventtime=None):
        return {'speed_factor': self.speed_factor, 'extrude_factor': self.extrude_factor}

class FakePrinter:
    def __init__(self):
        self.handlers = {}
        self.gcodeMove = FakeGcodeMove()

    def get_reactor(self):
        return types.SimpleNamespace(monotonic=time.monotonic)

    def register_event_handler(self, event, callback):
        self.handlers[event] = callback

    def lookup_object(self, name):
        assert name == 'gcode_move'
        return self.gcodeMove

    def send_event(self, event):
        self.handlers[event]()

#
# wait until condition is true, threads need some time to forward data
#
def waitFor(condition, timeout=2.):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()

CONFIG = {
    'tft_device': 'tft',
    'klipper_device': 'klippy',
    'tft_timeout': '0.05',
    'klipper_timeout': '0.05',
    'machine_extruder_count': '2',
    'machine_zprobe': '1',
    'machine_autolevel': '1',
    'machine_autoreport_pos': '0',
    'machine_autoreport_temp': '1',
}

class TftBridgeTestCase(unittest.TestCase):
    def setUp(self):
        FakePort.devices = {}
        patches = [
            mock.patch.object(tftbridge, 'serial', fakeSerial),
            mock.patch.object(tftbridge, 'RECONNECT_DELAY', 0.05),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.printer = FakePrinter()
        self.bridge = None

    def tearDown(self):
        if self.bridge is not None and self.bridge.threads:
            self.printer.send_event('klippy:disconnect')

    def addDevice(self, name):
        FakePort.devices[name] = (queue.Queue(), [])
        return FakePort.devices[name]

    def createBridge(self, values=CONFIG):
        self.config = FakeConfig(self.printer, dict(values))
        self.bridge = tftbridge.TftBridge(self.config)
        return self.bridge

    #
    # create bridge with both devices present and wait until it is connected
    #
    def startBridge(self):
        self.tftInput, self.tftOutput = self.addDevice('tft')
        self.klipperInput, self.klipperOutput = self.addDevice('klippy')
        self.createBridge()
        self.printer.send_event('klippy:ready')
        self.assertTrue(waitFor(lambda: self.bridge.tftSerial is not None and self.bridge.klipperSerial is not None))

    #
    # send line from TFT and wait for expected number of writes back to TFT
    #
    def sendFromTft(self, line, expectedWrites=1):
        self.tftInput.put(line)
        self.assertTrue(waitFor(lambda: len(self.tftOutput) >= expectedWrites),
                        f"no response to {line!r}, got {self.tftOutput!r}")
        return b''.join(self.tftOutput)

class ConfigTests(TftBridgeTestCase):
    def test_all_options_are_read(self):
        # Klipper refuses to start when a configured option is never read
        self.createBridge()
        self.assertEqual(set(CONFIG), self.config.accessed & set(CONFIG))

    def test_defaults(self):
        bridge = self.createBridge({'tft_device': 'tft', 'klipper_device': 'klippy'})
        self.assertEqual(250000, bridge.tftBaud)
        self.assertEqual(250000, bridge.klipperBaud)
        self.assertEqual(tftbridge.DEFAULT_TIMEOUT, bridge.tftTimeout)
        self.assertEqual(1, bridge.machine_extruder_count)
        self.assertEqual(0, bridge.machine_zprobe)
        self.assertEqual(0, bridge.machine_autoreport_temp)

    def test_devices_are_required(self):
        with self.assertRaises(KeyError):
            self.createBridge({'tft_device': 'tft'})

    def test_zero_timeout_uses_default(self):
        # blocking reads would keep threads from noticing stop requests
        self.addDevice('tft')
        port = self.createBridge().openDevice('tft', 250000, 0)
        self.assertEqual(tftbridge.DEFAULT_TIMEOUT, port.timeout)

class CustomCommandTests(TftBridgeTestCase):
    def setUp(self):
        super().setUp()
        self.startBridge()

    def test_m115_reports_capabilities(self):
        response = self.sendFromTft(b'M115\n')
        self.assertIn(b'FIRMWARE_NAME:Klipper EXTRUDER_COUNT:2\n', response)
        self.assertIn(b'Cap:Z_PROBE:1\n', response)
        self.assertIn(b'Cap:AUTOLEVEL:1\n', response)
        self.assertIn(b'Cap:AUTOREPORT_POS:0\n', response)
        self.assertIn(b'Cap:AUTOREPORT_TEMP:1\n', response)
        self.assertTrue(response.endswith(b'ok\n'))
        self.assertEqual([], self.klipperOutput)

    def test_command_matching_ignores_case_and_whitespace(self):
        response = self.sendFromTft(b' m115 \r\n')
        self.assertIn(b'FIRMWARE_NAME:Klipper', response)

    def test_m220_query_answered_locally(self):
        # bare M220 would reset Klipper speed factor to 100%
        self.printer.gcodeMove.speed_factor = 1.25
        self.assertEqual(b'FR:125%\nok\n', self.sendFromTft(b'M220\n'))
        self.assertEqual([], self.klipperOutput)

    def test_m221_query_answered_locally(self):
        self.printer.gcodeMove.extrude_factor = 0.9
        self.assertEqual(b'echo:E0 Flow: 90%\nok\n', self.sendFromTft(b'M221\n'))
        self.assertEqual([], self.klipperOutput)

    def test_m220_m221_with_value_forwarded(self):
        self.tftInput.put(b'M220 S110\n')
        self.tftInput.put(b'M221 S95\n')
        self.assertTrue(waitFor(lambda: self.klipperOutput == [b'M220 S110\n', b'M221 S95\n']))
        self.assertEqual([], self.tftOutput)

    def test_unsupported_commands_answered_locally(self):
        for command in (b'M92', b'M503', b'M500'):
            with self.subTest(command=command):
                self.tftOutput.clear()
                response = self.sendFromTft(command + b'\n')
                self.assertEqual(b'// Unknown command:"' + command + b'"\nok\n', response)
        self.assertEqual([], self.klipperOutput)

class ForwardingTests(TftBridgeTestCase):
    def setUp(self):
        super().setUp()
        self.startBridge()

    def test_tft_commands_forwarded_to_klipper(self):
        self.tftInput.put(b'G28 X\r\n')
        self.assertTrue(waitFor(lambda: self.klipperOutput == [b'G28 X\n']))

    def test_partial_line_joined_before_forwarding(self):
        self.tftInput.put(b'G1 X10')
        time.sleep(0.1)  # longer than read timeout, first part comes back alone
        self.tftInput.put(b' Y20\n')
        self.assertTrue(waitFor(lambda: self.klipperOutput == [b'G1 X10 Y20\n']))

    def test_partial_custom_command_still_matched(self):
        self.tftInput.put(b'M2')
        time.sleep(0.1)
        response = self.sendFromTft(b'20\n')
        self.assertTrue(response.startswith(b'FR:'))

    def test_empty_lines_ignored(self):
        self.tftInput.put(b'\n')
        self.tftInput.put(b'M105\n')
        self.assertTrue(waitFor(lambda: self.klipperOutput == [b'M105\n']))

    def test_klipper_output_forwarded_to_tft(self):
        self.klipperInput.put(b'ok B:60.0 /60.0 T0:200.0 /200.0\n')
        self.assertTrue(waitFor(lambda: self.tftOutput == [b'ok B:60.0 /60.0 T0:200.0 /200.0\n']))

class ConnectionTests(TftBridgeTestCase):
    def test_waits_for_missing_port_then_connects(self):
        self.addDevice('klippy')
        self.createBridge()
        with self.assertLogs(level='WARNING') as logs:
            self.printer.send_event('klippy:ready')
            time.sleep(0.3)  # several reconnect attempts
        self.assertIsNone(self.bridge.tftSerial)
        self.assertEqual(1, len(logs.records), "open failure should be logged only once")

        tftInput, tftOutput = self.addDevice('tft')
        self.assertTrue(waitFor(lambda: self.bridge.tftSerial is not None))
        tftInput.put(b'M115\n')
        self.assertTrue(waitFor(lambda: tftOutput))

    def test_reopens_ports_after_error(self):
        self.startBridge()
        failedPort = self.bridge.tftSerial
        with self.assertLogs(level='ERROR'):
            failedPort.close()  # next read raises
            self.assertTrue(waitFor(lambda: self.bridge.tftSerial not in (None, failedPort)))
        self.sendFromTft(b'M115\n')

    def test_disconnect_stops_threads_and_closes_ports(self):
        self.startBridge()
        tftSerial, klipperSerial = self.bridge.tftSerial, self.bridge.klipperSerial
        threads = list(self.bridge.threads)
        self.assertTrue(all(thread.daemon for thread in threads))

        started = time.monotonic()
        self.printer.send_event('klippy:disconnect')
        self.assertLess(time.monotonic() - started, tftbridge.STOP_TIMEOUT)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertTrue(tftSerial.closed and klipperSerial.closed)
        self.assertIsNone(self.bridge.tftSerial)
        self.assertIsNone(self.bridge.klipperSerial)

    def test_restart_does_not_leave_competing_readers(self):
        self.startBridge()
        self.printer.send_event('klippy:disconnect')
        # Klipper creates a new instance on restart
        self.createBridge()
        self.printer.send_event('klippy:ready')
        self.assertTrue(waitFor(lambda: self.bridge.tftSerial is not None))
        bridgeThreads = [t for t in threading.enumerate() if t.name != threading.main_thread().name]
        self.assertEqual(2, len(bridgeThreads))

if __name__ == '__main__':
    unittest.main()
