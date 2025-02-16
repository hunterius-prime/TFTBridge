# tftbridge
This Klipper add-on allows you to use the BigTreeTech TFT (v3.0) display with Klipper in touch screen mode. TFT28, TFT35, TFT43 to TFT70, based on work of oldhui.wordpress.com. 
Part of this project will be modified firmware for TFT display ( right now still not mandatory)

# Implemented Features

As it is still "work-in-progress" project, please do not expect everything translated.
So far if implemented or working out of the box:
- temperature control and monitoring
- movement control and monitoring
- fans control
- homing 
- Z tilt adjustment 
- basic printer capabilities reporting for enabling parts of menu based on enabled capabilities 
- BLTouch menu / control
- printing from SDCARD or USB (not perfect but 80% usable)


## Hardware Connection
For the general idea of the connection and hardware connection, please refer to [my post here](https://oldhui.wordpress.com/2024/01/28/using-btt-tft35-with-klipper-in-touch-mode/).


## Software Setup

A standard installation of Klipper puts the system into the `pi` user account.
Host add-ons will be in the  `/home/pi/klipper/klippy/extras` folder.
To install `tftbridge` as a Klipper add-on:

1. Copy `tftbridge.py` into `/home/pi/klipper/klippy/extras`
1. In your standard printer.cfg file, add the following section:

```
[tftbridge]
tft_device: /dev/ttyAMA0
tft_baud: 250000
tft_timeout: 0
klipper_device: /home/pi/printer_data/comms/klippy.serial
klipper_baud: 250000
klipper_timeout: 0

machine_extruder_count : 1
machine_zprobe : 1
machine_autoreport_pos : 0
machine_autoreport_temp : 1
machine_autolevel : 1
```

If your configuration is different, you may need to customise the above settings.
`ttf_device` is based on your hardware connection on PI board.
froo example, in OrangePI Zero and UART1 serial connection it will be `/dev/ttyS1`


## Running the Add-on
Restart the Klipper service to run the add-on:
```
sudo service klipper start
```

You should see Klipper starting as usual. A while later, the TFT35 should show "printer connected" in Touch Screen mode.

## Limitations
All features from marlin-based display are not implemented yet, list of working features will be updated accordingly. Feel free to test an report issues.
`Important` - printing from TFT (SD CARD or USB) is limited to 100 characters per command (including \n ) so "massive" klipper START_PRINT comand can in some cases break print. Printing from host is unaffected of course. 

## What next
Ultimate goal is to be able to make basic interaction with printer from TFT touchscreen, so after polishing commands for live adjustments, next step will be printing management. TFTBridge is even now usable to some degree. 
It is also possible that TFT firmware will be modified to better suit Klipper printing.