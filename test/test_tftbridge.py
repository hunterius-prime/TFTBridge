#
#Bridging BTT TFT35 and Klipper.#
#K. Hui (06/01/2024), Hunterius
#

import serial
import threading
import configparser

#
# Load configuration
#
config = configparser.ConfigParser()
config.read('test_config.ini')

tftPort = config.get('printer', 'tft_device')
tftBaud = config.getint('printer', 'tft_baud')
tftTimeout = config.getint('printer', 'tft_timeout')
printerPort = config.get('printer', 'klipper_device')
printerBaud = config.getint('printer', 'klipper_baud')
printerTimeout = config.getint('printer', 'klipper_timeout')
machine_extruder_count = config.getint('printer', 'machine_extruder_count')
machine_zprobe = config.getint('printer', 'machine_zprobe')
machine_autoreport_pos = config.getint('printer', 'machine_autoreport_pos')
machine_autoreport_temp = config.getint('printer', 'machine_autoreport_temp')
machine_autolevel = config.getint('printer', 'machine_autolevel')

#
# Open a serial port
#
def openSerial(port, baud, timeout):
    if timeout == 0:
        tft = serial.Serial(port, baud)
    else:
        tft = serial.Serial(port, baud, timeout=timeout)
    return tft

#
# Handle custom commands
#
def handle_custom_commands(line, tftSerial):
    if line == b'M115\n':
        response = (
            f"FIRMWARE_NAME:Marlin EXTRUDER_COUNT:{machine_extruder_count}\n"
            f"Cap:AUTOLEVEL:{machine_autolevel}\n"
            f"Cap:EEPROM:0\n"
            f"Cap:Z_PROBE:{machine_zprobe}\n"
            f"Cap:LEVELING_DATA:1\n"
            f"Cap:AUTOREPORT_POS:{machine_autoreport_pos}\n"
            f"Cap:AUTOREPORT_TEMP:{machine_autoreport_temp}\n"
        )
        
        tftSerial.write(response.encode('utf-8'))
        tftSerial.write(b'ok\n')
        print('Responding with M115 custom response')
        print(response.encode('utf-8'))
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
        tftSerial.write(response.encode('utf-8'))
        tftSerial.write(b'ok\n')
        print(f'Responding with OK for {command}')
        return True
    
    return False

#
# Translate incoming commands
#
def translate_command(line):
    command_mapping = {
        b'G34\n': b'Z_TILT_ADJUST\n',
        b'M108\n': b'CANCEL_PRINT\n',
        # Add more commands as needed
    }
    
    return command_mapping.get(line, line)

#
# Print method with suppression checks
#
def print_filtered(tag, line):
    suppress_list = [b'ok\n', b'echo:busy: processing\n',b'M220\n',b'M221\n',b'M114\n']

    if line not in suppress_list:
        print(f'{tag}: ', line)

#
# Read input from TFT and forward it to Klipper
#
def tft2klipper(tftSerial, klipperSerial):
    while True:
        line = tftSerial.readline()
        print_filtered('tft->Klipper: ', line)

        # Check for custom commands and respond and not process further
        if handle_custom_commands(line, tftSerial):
            continue
        
        # Translate the command if needed to kliper format
        line = translate_command(line)

        klipperSerial.write(line)

#
# Read output from Klipper and forward it to TFT
# 
def klipper2tft(tftSerial, klipperSerial):
    while True:
        line = klipperSerial.readline()
        print_filtered('Klipper->tft: ', line)
        tftSerial.write(line)

def main():
    tftSerial = openSerial(tftPort, tftBaud, tftTimeout)
    klipperSerial = openSerial(printerPort, printerBaud, printerTimeout)
    t1 = threading.Thread(target=tft2klipper, args=(tftSerial, klipperSerial))
    t2 = threading.Thread(target=klipper2tft, args=(tftSerial, klipperSerial))
    t1.start()
    t2.start()

if __name__ == "__main__":
    main()
