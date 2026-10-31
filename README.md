# tftbridge
This Klipper add-on allows you to use the BigTreeTech TFT (v3.0) display with Klipper in touch screen mode. TFT28, TFT35, TFT43 to TFT70, based on work of oldhui.wordpress.com. 
Part of this project will be modified firmware for TFT display ( right now still not mandatory)

# Implemented Features

As it is still "work-in-progress" project, please do not expect everything translated.
So far is implemented or working out of the box:
- temperature control and monitoring
- movement control and monitoring
- fans control
- speed and flow percentage (display and adjustment)
- homing 
- Z tilt adjustment 
- basic printer capabilities reporting for enabling parts of menu based on enabled capabilities 
- BLTouch menu / control
- printing from SDCARD slot on TFT or USB (not perfect but 80% usable)
- printing from host(klipper) file list , PAUSE/RESUME working


## Hardware Connection
For the general idea of the connection and hardware connection, please refer to [original author post here](https://oldhui.wordpress.com/2024/01/28/using-btt-tft35-with-klipper-in-touch-mode/).


## Software Setup

A standard installation of Klipper puts the system into the `pi` user account.
Host add-ons will be in the  `/home/pi/klipper/klippy/extras` folder.
To install `tftbridge` as a Klipper add-on:

1. Copy `tftbridge.py` into `/home/pi/klipper/klippy/extras`
1. Copy `tftbridge.cfg` into `/home/pi/printer_data/config`
1. In your standard printer.cfg file (or in overrides.cfg in case you are using klippain), add the following section:

```
#-------------------------#
#   CUSTOM TFT GCODE      #
#-------------------------#
## for BTT TFT integration
[include tftbridge.cfg]
```

If your configuration is different, you may need to customize the above settings.
`tft_device` is based on your hardware connection on PI board.
For example, in OrangePI Zero and UART1 serial connection it will be `/dev/ttyS1`

### Configuration options

| Option | Default | Description |
|---|---|---|
| `tft_device` | (required) | Serial port the TFT is connected to, e.g. `/dev/ttyS1` |
| `tft_baud` | `250000` | Must match `serial_port` in the TFT `config.ini` (`P1:8` = 250000) |
| `tft_timeout` | `1` | Read timeout in seconds. `0` is treated as `1`, so the bridge can stop cleanly on restart |
| `klipper_device` | (required) | Klipper pseudo-tty, e.g. `/home/pi/printer_data/comms/klippy.serial` |
| `klipper_baud` | `250000` | Ignored by the pseudo-tty, kept for completeness |
| `klipper_timeout` | `1` | Same as `tft_timeout` |
| `machine_extruder_count` | `1` | Reported to the TFT in `M115` |
| `machine_zprobe` | `0` | `1` enables probe menus on the TFT |
| `machine_autolevel` | `0` | `1` enables leveling menus on the TFT |
| `machine_autoreport_pos` | `0` | Leave at `0`, Klipper does not support `M154` |
| `machine_autoreport_temp` | `0` | Leave at `0`, Klipper does not support `M155` (the TFT polls `M105` instead) |

### Klipper requirements
- Klipper must be started with the `-I <path>/klippy.serial` option (standard in KIAUH / printer_data installs); `klipper_device` points to that file.
- The macros in `tftbridge.cfg` need these Klipper sections in your configuration:
  - `[virtual_sdcard]` and `[pause_resume]` for `M24` / `M25` (pause / resume)
  - `[z_tilt]` for `G34`
  - `[bltouch]` for `M280` (BLTouch menu)
  - a `CANCEL_PRINT` macro for `M524` (included in most configurations, e.g. Mainsail / Fluidd)

  Remove the macros you don't need if your printer doesn't have the matching section.


## Running the Add-on
Restart the Klipper service to run the add-on:
```
sudo service klipper restart
```

You should see Klipper starting as usual. A while later, the TFT35 should show "printer connected" in Touch Screen mode.

## Development

### Running tests
Unit tests use fake serial ports and Klipper objects, so they run on any PC with Python 3 (no Klipper, pyserial or TFT needed):
```
python -m unittest discover test
```

### Sniffing TFT traffic
`test/tft_sniffer.py` is a standalone bridge that prints all traffic between the TFT and Klipper. Stop Klipper's `tftbridge` first (it uses the same ports), adjust `test/test_config.ini` and run it from the `test` folder:
```
cd test
python3 tft_sniffer.py
```

## Limitations
All features from marlin-based display are not implemented yet, list of working features will be updated accordingly. Feel free to test an report issues.
`Important` - printing from TFT (SD CARD or USB) is limited to 100 characters per command (including \n ) so "massive" klipper START_PRINT comand can in some cases break print. Printing from host is unaffected of course. 

## What next
Ultimate goal is to be able to make basic interaction with printer from TFT touchscreen, so after polishing commands for live adjustments, next step will be printing management. TFTBridge is even now usable to some degree. 
It is also possible that TFT firmware will be modified to better suit Klipper printing.