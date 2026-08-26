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


def _pack32(buf, off, val):
    buf[off] = val & 0xff
    buf[off + 1] = (val >> 8) & 0xff
    buf[off + 2] = (val >> 16) & 0xff
    buf[off + 3] = (val >> 24) & 0xff


# Push the whole framebuffer to the display via the SPI hardware FIFO.
# Param block (20 bytes): [src, lut, spi_base, staging, nbatches]
# Staging approach: convert nibbles to RGB565 in DRAM, wait for SPI idle,
# burst-copy staging->FIFO, trigger.
# Register map:
#   a2  = batch counter / param pointer (reused)
#   a3  = src pointer (4bpp nibble stream, consumed forward)
#   a4  = fifo_lut base (256 x 4-byte CLUT words)
#   a5  = spi base address
#   a6  = staging buffer address (64 bytes, DRAM)
#   a7  = FIFO W0 base (spi + 0x80)
#   a8  = USR trigger bit (0x040000)
#   a9  = staging/copy pointer (reset each loop)
#   a10 = FIFO write pointer (reset each loop)
#   a11 = constant 16 (batch size)
#   a14 = loop counter
#   a15 = scratch
@micropython.asm_xtensa
def _show_fifo(a2):

    l32i(a3, a2, 0)          # a3 = src
    l32i(a4, a2, 4)          # a4 = lut
    l32i(a5, a2, 8)          # a5 = spi base
    l32i(a6, a2, 12)         # a6 = staging ptr
    l32i(a2, a2, 16)         # a2 = nbatches (overwrites param ptr)
    movi(a8, 0x040000)       # SPI_USR bit in cmd reg
    movi(a11, 16)            # 16 words per batch
    movi(a15, 511)
    s32i(a15, a5, 0x28)      # DLEN = 511 bits (64 bytes)
    movi(a7, 0x80)
    add(a7, a5, a7)          # a7 = spi + 0x80 = W0 FIFO

    # -- outer loop: 2400 batches ------------------------------------
    label(batch)                                       # batch --+
                                                       #        |
    # -- inner loop 1: convert 16 nibbles -> staging -----
    mov(a9, a6)                                        # staging ptr
    mov(a14, a11)                                      # counter = 16
    label(cv)                                          # cv -----+
    l8ui(a15, a3, 0)          # read nibble byte       # |        |
    addi(a3, a3, 1)           # advance src            # |        |
    addx4(a15, a15, a4)       # byte * 4 + lut base    # |        |
    l32i(a15, a15, 0)         # load 2xRGB565 word     # |        |
    s32i(a15, a9, 0)          # store to staging       # |        |
    addi(a9, a9, 4)           # advance staging ptr    # |        |
    addi(a14, a14, -1)                                 # |        |
    bnez(a14, cv)                                      # ---------+

    # -- poll: wait for previous SPI transfer to finish --------
    label(wi)                                          # wi -----+
    l32i(a15, a5, 0)           # read SPI_CMD          # |        |
    bbsi(a15, 18, wi)          # while USR bit set     # ---------+

    # -- burst-copy 16 words staging -> FIFO ---------------------
    mov(a9, a6)                                        # staging base
    mov(a10, a7)                                       # FIFO W0 base
    mov(a14, a11)                                      # counter = 16
    label(cp)                                          # cp -----+
    l32i(a15, a9, 0)           # load from staging     # |        |
    s32i(a15, a10, 0)          # store to FIFO         # |        |
    addi(a10, a10, 4)          # advance FIFO ptr      # |        |
    addi(a9, a9, 4)            # advance staging ptr   # |        |
    addi(a14, a14, -1)                                 # |        |
    bnez(a14, cp)                                      # ---------+

    # trigger the 512-bit transfer
    s32i(a8, a5, 0)            # set SPI_USR

    addi(a2, a2, -1)           # decrement batch counter
    bnez(a2, batch)            # ----------------------- # +------+

    # drain the final transfer
    label(wf)                                          # wf -----+
    l32i(a15, a5, 0)           # read SPI_CMD          # |        |
    bbsi(a15, 18, wf)          # while USR bit set     # ---------+


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
        # 64-byte staging buffer for burst copy to SPI FIFO
        self._staging = bytearray(64)
        # Parameter block for asm: [src, lut, spi, staging, nbatches]
        self._params = bytearray(20)

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

        # Pack param block
        p = self._params
        _pack32(p, 0, uctypes.addressof(self.buf))
        _pack32(p, 4, uctypes.addressof(self.fifo_lut))
        _pack32(p, 8, _SPI_BASE)
        _pack32(p, 12, uctypes.addressof(self._staging))
        _pack32(p, 16, (width * height * 2) // 64)
        self._pa = uctypes.addressof(self._params)

        self.init_display()
        self._set_window(0, 0, self.width - 1, self.height - 1)

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
        self._cmd(RASET, [y0 >> 8, y0 & 0xff, x1 >> 8, y1 & 0xff])
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
        """Push the whole framebuffer to the display."""
        self.dc.value(1)
        self.cs.value(0)
        _show_fifo(self._pa)
        self.cs.value(1)
