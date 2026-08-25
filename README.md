# fb4

A fast 4-bit indexed framebuffer driver for MicroPython on the ESP32 Cheap Yellow Display (CYD) with ST7789 TFT.

## Features

- **GS4_HMSB framebuffer** -- 4 bits per pixel, 16-color indexed palette
- **asm_xtensa SPI-FIFO show()** -- streams palette-converted RGB565 directly into the SPI hardware FIFO for ~30 ms full-screen updates
- **Standard MicroPython framebuf API** -- use `fill`, `text`, `line`, `rect`, `blit`, etc. as normal, then call `show()` to push to the LCD
- Portrait or landscape via `madctl` parameter

## Hardware

Designed for the **ESP32-2432S028R** (Cheap Yellow Display):

| Pin | GPIO | Function |
|-----|------|----------|
| SCK | 14 | SPI clock |
| MOSI | 13 | SPI data |
| DC | 2 | Data/Command |
| CS | 15 | Chip Select |
| RST | 4 | Reset |
| BL | 21 | Backlight |

## Quick Start

Copy `fb4.py` to your MicroPython device, then:

```python
import fb4

d = fb4.FB4()
d.fill(0)
d.text("HELLO CYD", 80, 110, 9)  # 9 = white
d.show()
```

### Palette

```python
d.set_palette(1, 255, 0, 0)   # index 1 = red
d.set_palette(9, 255, 255, 255)  # index 9 = white
```

### Portrait mode

```python
d = fb4.FB4(width=240, height=320, madctl=0x00)
```

## Examples

Game demos in `examples/`:

| Game | Screenshot |
|------|------------|
| `fb4_pillman.py` | ![pillman](screenshots/fb4_pillman.png) |
| `fb4_rock_runner.py` | ![rock_runner](screenshots/fb4_rock_runner.png) |
| `fb4_crater_crawler.py` | ![crater_crawler](screenshots/fb4_crater_crawler.png) |
| `fb4_space_intruders.py` | ![space_intruders](screenshots/fb4_space_intruders.png) |
| `fb4_serpent.py` | ![serpent](screenshots/fb4_serpent.png) |
| `fb4_gp.py` | ![gp](screenshots/fb4_gp.png) |
| `fb4_kessler.py` | ![kessler](screenshots/fb4_kessler.png) |
| `fb4_dashboard1.py` | ![dashboard1](screenshots/fb4_dashboard1.png) |
| `fb4_dashboard2.py` | ![dashboard2](screenshots/fb4_dashboard2.png) |
| `fb4_weather.py` | ![weather](screenshots/fb4_weather.png) |

## How It Works

The driver allocates a `width * height / 2` byte buffer in GS4_HMSB format. When `show()` is called, a precomputed 256-entry lookup table (one byte pair to two RGB565 pixels) is used by an inline assembly loop that reads 64 bytes at a time and writes them directly to the SPI1 FIFO registers, bypassing the Python interpreter entirely.

## Firmware

fb4 requires a custom MicroPython v1.29.0 build with the inline Xtensa assembler enabled (`MICROPY_EMIT_INLINE_XTENSA=1`). The stock MicroPython binary from micropython.org does not include this feature.

Pre-built firmware binaries are in `firmware/`.

### Building with mpbuild

[mpbuild](https://github.com/mattytrentini/mpbuild) builds MicroPython firmware in Docker containers -- no toolchains to install.

```bash
# Install mpbuild
uv tool install mpbuild

# Clone MicroPython (with submodules)
git clone --recursive --branch v1.29.0 https://github.com/micropython/micropython.git
cd micropython

# Enable inline Xtensa assembler in board config
# (add the following line after the existing #defines in ports/esp32/boards/ESP32_GENERIC/mpconfigboard.h):
#   #define MICROPY_EMIT_INLINE_XTENSA (1)

# Build
mpbuild build ESP32_GENERIC

# Merge into single firmware binary
python -m esptool --chip esp32 merge_bin --flash_mode dio --flash_size 4MB --flash_freq 40m \
  -o ports/esp32/build-ESP32_GENERIC/micropython_v1.29.0.bin \
  0x1000 ports/esp32/build-ESP32_GENERIC/bootloader/bootloader.bin \
  0x8000 ports/esp32/build-ESP32_GENERIC/partition_table/partition-table.bin \
  0x10000 ports/esp32/build-ESP32_GENERIC/micropython.bin
```

### Flashing

```bash
# Erase flash (one-time)
python -m esptool --chip esp32 erase_flash

# Flash firmware
python -m esptool --chip esp32 -b 460800 --before default_reset --after hard_reset \
  write_flash --flash_mode dio --flash_size 4MB --flash_freq 40m \
  0x0 firmware/micropython_v1.29.0.bin
```

### Deploying Files

After flashing, copy `fb4.py` and any example to the device:

```bash
mpremote connect /dev/ttyUSB0 cp src/fb4.py :fb4.py
mpremote connect /dev/ttyUSB0 cp examples/fb4_weather.py :main.py
```

## License

MIT
