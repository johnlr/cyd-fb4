# fb4.py - Reusable 4-bit indexed framebuffer driver for CYD ST7789 (ESP32)
#
# Provides a framebuf.GS4_HMSB framebuffer (4 bits/pixel, 16-color palette)
# and a fast show() that converts palette indices to RGB565 and streams the
# result straight into the SPI hardware FIFO using inline Xtensa assembly.
#
# Usage:
#   import fb4
#   d = fb4.FB4()
#   d.fill(0)
#   d.text("HELLO", 10, 10, 9)        # index 9 = white
#   d.set_palette(1, 255, 0, 0)       # optional palette change
#   d.show()

from machine import Pin, SPI
import framebuf
import uctypes
import time

SWRESET = 0x01; SLPOUT = 0x11; NORON = 0x13
INVOFF = 0x20; DISPON = 0x29
CASET = 0x2A; RASET = 0x2B; RAMWR = 0x2C
COLMOD = 0x3A; MADCTL = 0x36

_SPI_BASE = 0x3FF64000  # HSPI (SPI1) register base on ESP32


def color565(r, g, b):
    return ((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3)


# Push the whole framebuffer to the display via the SPI hardware FIFO.
# a2 = src (4bpp buffer), a3 = fifo_lut (256 x 4-byte packed words),
# a4 = SPI base address, a5 = number of 64-byte batches (2400 = 153600/64).
# NOTE: only backwards bnez loops are used (forward branches are broken in
# MicroPython's inline xtensa emitter); scratch regs limited to a6-a10.
@micropython.asm_xtensa
def _show_fifo(a2, a3, a4, a5):
    movi(a6, 511)
    s32i(a6, a4, 0x28)  # DLEN = 511 bits (64 bytes per batch)

    label(batch_loop)

    # 1. Wait for SPI idle
    label(wait_spi)
    l32i(a6, a4, 0x00)
    movi(a7, 0x40000)
    and_(a6, a6, a7)
    bnez(a6, wait_spi)

    # 2. Feed 16 words (64 bytes) from precomputed LUT into SPI_W0..W15
    movi(a6, 0)        # FIFO offset counter
    movi(a7, 16)       # 16 words per batch

    label(conv_loop)
    l8ui(a8, a2, 0)    # read 1 input byte (2 pixels)
    addi(a2, a2, 1)    # src++

    slli(a9, a8, 2)    # byte * 4 = LUT index
    add(a9, a9, a3)
    l32i(a9, a9, 0)    # load pre-packed 32-bit word (2 pixels RGB565)

    add(a8, a4, a6)
    s32i(a9, a8, 0x80) # store into SPI FIFO register W0..W15

    addi(a6, a6, 4)
    addi(a7, a7, -1)
    bnez(a7, conv_loop)

    # 3. Trigger transfer
    movi(a6, 0x040000)
    s32i(a6, a4, 0x00)

    addi(a5, a5, -1)
    bnez(a5, batch_loop)

    # Final wait for last batch to drain
    label(wait_final)
    l32i(a6, a4, 0x00)
    movi(a7, 0x040000)
    and_(a6, a6, a7)
    bnez(a6, wait_final)


class FB4(framebuf.FrameBuffer):
    """A 4-bit indexed framebuffer that is itself a FrameBuffer.

    Draw with the normal FrameBuffer methods (fill, text, line, ...) using
    palette indices 0-15 as colors, then call show() to push it to the LCD.
    """

    def __init__(self, width=320, height=240, baudrate=80000000,
                 spi_id=1, sck=14, mosi=13, dc=2, cs=15, rst=4, bl=21,
                 madctl=0xA0):
        self.width = width
        self.height = height
        self.madctl = madctl

        self.bl = Pin(bl, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT)
        self.cs = Pin(cs, Pin.OUT)
        self.rst = Pin(rst, Pin.OUT)
        self.spi = SPI(spi_id, baudrate=baudrate, sck=Pin(sck), mosi=Pin(mosi))

        # 4-bit framebuffer: width*height/2 bytes
        self.buf = bytearray(width * height // 2)
        super().__init__(self.buf, width, height, framebuf.GS4_HMSB)

        # 16-entry palette, RGB565 stored MSB-first
        self.clut = bytearray(32)
        # Precomputed LUT: input byte -> 4-byte word with 2 pre-swapped pixels
        self.fifo_lut = bytearray(256 * 4)

        # Default 16-color palette
        palette = (
            (0, 0, 0),          # 0 black
            (255, 0, 0),        # 1 red
            (0, 255, 0),        # 2 green
            (0, 0, 255),        # 3 blue
            (255, 255, 0),      # 4 yellow
            (0, 255, 255),      # 5 cyan
            (255, 0, 255),      # 6 magenta
            (255, 165, 0),      # 7 orange
            (128, 0, 128),      # 8 purple
            (255, 255, 255),    # 9 white
            (128, 0, 0),        # 10 maroon
            (0, 255, 128),      # 11 spring green
            (0, 0, 128),        # 12 navy
            (0, 128, 128),      # 13 teal
            (255, 192, 203),    # 14 pink
            (128, 128, 128),    # 15 gray
        )
        for i, (r, g, b) in enumerate(palette):
            self.set_palette(i, r, g, b)

        self._src = uctypes.addressof(self.buf)
        self._lut = uctypes.addressof(self.fifo_lut)
        self._batches = (width * height * 2) // 64

        self.init_display()

    def set_palette(self, i, r, g, b):
        """Set palette entry i (0-15) to the given RGB and rebuild the LUT."""
        c = color565(r, g, b)
        self.clut[i * 2] = c >> 8
        self.clut[i * 2 + 1] = c & 0xff
        self._rebuild_lut()

    def _rebuild_lut(self):
        # Pack two pre-byte-swapped RGB565 pixels per input byte so the asm
        # loop can copy one LUT word straight into the SPI FIFO.
        clut = self.clut
        lut = self.fifo_lut
        for i in range(256):
            hi = i >> 4
            lo = i & 15
            c1_lo = clut[hi * 2 + 1]
            c1_hi = clut[hi * 2]
            c2_lo = clut[lo * 2 + 1]
            c2_hi = clut[lo * 2]
            val = c1_lo | (c1_hi << 8) | (c2_lo << 16) | (c2_hi << 24)
            o = i * 4
            lut[o] = val & 0xff
            lut[o + 1] = (val >> 8) & 0xff
            lut[o + 2] = (val >> 16) & 0xff
            lut[o + 3] = (val >> 24) & 0xff

    def _cmd(self, c, d=None):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytes([c]))
        if d is not None:
            self.dc.value(1)
            self.spi.write(bytes(d))
        self.cs.value(1)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(CASET, [x0 >> 8, x0 & 0xff, x1 >> 8, x1 & 0xff])
        self._cmd(RASET, [y0 >> 8, y0 & 0xff, y1 >> 8, y1 & 0xff])
        self._cmd(RAMWR)

    def init_display(self):
        rst = self.rst
        rst.value(0); time.sleep_ms(50); rst.value(1); time.sleep_ms(50)
        self._cmd(SWRESET); time.sleep_ms(150)
        self._cmd(SLPOUT); time.sleep_ms(50)
        self._cmd(COLMOD, [0x55]); time.sleep_ms(10)
        self._cmd(MADCTL, [self.madctl])
        self._cmd(INVOFF)
        self._cmd(NORON); time.sleep_ms(10)
        self._cmd(DISPON); time.sleep_ms(50)

    def show(self):
        """Push the whole framebuffer to the display (~30 ms)."""
        self._set_window(0, 0, self.width - 1, self.height - 1)
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(bytearray(1))
        _show_fifo(self._src, self._lut, _SPI_BASE, self._batches)
        self.cs.value(1)
