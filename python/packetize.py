#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# Copyright 2014 Clayton Smith.
# 
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this software; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

import numpy
import struct
from gnuradio import gr
from datetime import datetime


def xtea_decrypt(key,block,n=32,endian="!"):
    """
        Decrypt 64 bit data block using XTEA block cypher
        * key = 128 bit (16 char)
        * block = 64 bit (8 char)
        * n = rounds (default 32)
        * endian = byte order (see 'struct' doc - default big/network)

        >>> z = 'b67c01662ff6964a'.decode('hex')
        >>> xtea_decrypt('0123456789012345',z)
        'ABCDEFGH'

        Only need to change byte order if sending/receiving from
        alternative endian implementation

        >>> z = 'ea0c3d7c1c22557f'.decode('hex')
        >>> xtea_decrypt('0123456789012345',z,endian="<")
        'ABCDEFGH'

    """
    v0,v1 = struct.unpack(endian+"2L",block)
    k = struct.unpack(endian+"4L",key)
    delta,mask = 0x9e3779b9L,0xffffffffL
    sum = (delta * n) & mask
    for round in range(n):
        v1 = (v1 - (((v0<<4 ^ v0>>5) + v0) ^ (sum + k[sum>>11 & 3]))) & mask
        sum = (sum - delta) & mask
        v0 = (v0 - (((v1<<4 ^ v1>>5) + v1) ^ (sum + k[sum & 3]))) & mask
    return struct.pack(endian+"2L",v0,v1)


class packetize(gr.basic_block):
    """
    docstring for block packetize
    """

    # 0000 1100 1001 1010 1001 0011
    sync_word = numpy.array([0,1, 0,1, 0,1, 0,1, 1,0, 1,0, 0,1, 0,1, 1,0, 0,1, 0,1, 1,0, 1,0, 0,1, 1,0, 0,1, 1,0, 0,1, 0,1, 1,0, 0,1, 0,1, 1,0, 1,0],dtype=numpy.int8).tostring()

    key1 = struct.pack(">4L", 0x58C1FA95, 0x26DACE48, 0xFF34088C, 0xA47564E2)
    key2 = struct.pack(">4L", 0x211D5B80, 0x5230C9CD, 0x8BA2EF63, 0x13D7BE02)

    icao_table = {
        "c06edf": ("C-GPZQ", "LS4",   "84"),
        "c02487": ("C-FNVQ", "ASW20", "VQ"),
        "c003b6": ("C-GBKN", "ASW20", "MZ"),
        "c081b6": ("C-GXDD", "SZD55", "2D"),
        "c06914": ("C-GNUP", "SZD55", "55"),
        "c0789b": ("C-GTRM", "ASW20", "RM"),
        "c05fdd": ("C-GKHU", "ASW24", "M7"),
        "c06208": ("C-GLDF", "LAK12", "Z7"),
        "c007be": ("C-FCYF", "SZD55", "AT"),
        "c06b5f": ("C-GORE", "PIK20", "GP")
    }

    def __init__(self, channel):
        gr.basic_block.__init__(self,
            name="packetize",
            in_sig=[numpy.int8],
            out_sig=[])
        self.channel = channel

    def forecast(self, noutput_items, ninput_items_required):
        ninput_items_required[0] = 5000

    def manchester_demod_packet(self, man_bits):
        for x in range(0, len(man_bits), 2):
            if man_bits[x] == man_bits[x+1]:
                # Manchester error. Discard packet.
                break
        else:
            # We've got a valid packet! Throw out the preamble and SFD
            # and extract the bits from the Manchester encoding.
            self.process_packet(man_bits[0::2])

    def process_packet(self, bits):
        bytes = numpy.packbits(bits)
        if self.crc16(bytes) == 0:
            bytes = self.decrypt_packet(bytes)
            icao, lat, lon, alt, vs, stealth, typ, ns, ew = self.extract_values(bytes[3:27])

            print datetime.now().isoformat(),
            print "Ch.{0:02}".format(self.channel),
            #print "{0:02x}{1:02x}{2:02x}".format(*bytes[0:3]),
            print "ICAO: " + icao,
            print "Lat: " + str(lat),
            print "Lon: " + str(lon),
            print "Alt: " + str(alt) + "m",
            print "VS: " + str(vs),
            print "Stealth: " + str(stealth),
            print "Type: " + str(typ),
            print "North/South speeds: {0},{1},{2},{3}".format(*ns),
            print "East/West speeds: {0},{1},{2},{3}".format(*ew),
            print "Raw: {0:02x}".format(bytes[6]),
            print "{0:02x}{1:02x}{2:02x}{3:02x}{4:02x}{5:02x}{6:02x}{7:02x}".format(*bytes[7:15]),
            print "{0:02x}{1:02x}{2:02x}{3:02x}{4:02x}{5:02x}{6:02x}{7:02x}".format(*bytes[15:23]),
            print "{0:02x}{1:02x}{2:02x}{3:02x}".format(*bytes[23:27]),
            #print "{0:02x}{1:02x}".format(*bytes[27:29]),
            if icao in self.icao_table:
                reg, typ, tail = self.icao_table[icao]
                print "(Reg: " + reg + ", Type: " + typ + ", Tail: " + tail + ")",
            print

    def crc16(self, message):
        poly = 0x1021
        reg = 0xffff
        for byte in message:
            mask = 0x80
            while mask != 0:
                reg <<= 1
                if byte & mask:
                    reg ^= 1
                mask >>= 1
                if reg & 0x10000 != 0:
                    reg &= 0xffff
                    reg ^= poly
        reg ^= 0x9335
        return reg

    def decrypt_packet(self, bytes):
        block = xtea_decrypt(self.key1, struct.pack("<2L", (bytes[7] << 24) | (bytes[8] << 16) | (bytes[9] << 8) | bytes[10], (bytes[11] << 24) | (bytes[12] << 16) | (bytes[13] << 8) | bytes[14]), n=6)
        for i in range(4):
            bytes[10-i] = ord(block[i])
            bytes[14-i] = ord(block[i+4])
        block = xtea_decrypt(self.key2, struct.pack("<2L", (bytes[15] << 24) | (bytes[16] << 16) | (bytes[17] << 8) | bytes[18], (bytes[19] << 24) | (bytes[20] << 16) | (bytes[21] << 8) | bytes[22]), n=6)
        for i in range(4):
            bytes[18-i] = ord(block[i])
            bytes[22-i] = ord(block[i+4])
        return bytes

    def extract_values(self, bytes):
        icao = "{0:02x}{1:02x}{2:02x}".format(bytes[2], bytes[1], bytes[0])
        lat = (bytes[5] << 8) | bytes[4]
        lon = (bytes[7] << 8) | bytes[6]
        alt = ((bytes[9] & 0x1f) << 8) | bytes[8]
        vs = ((bytes[10] & 0x7f) << 3) | ((bytes[9] & 0xe0) >> 5)
        vsmult = ((bytes[21] & 0xc0) >> 6)
        if vs < 0x200:
            vs = (vs << vsmult)
        else:
            vs -= 0x400
        stealth = ((bytes[11] & 0x80) == 0x80)
        typ = ((bytes[11] & 0x3C) >> 2)
        ns = [b if b < 0x80 else (b - 0x100) for b in bytes[12:16]]
        ew = [b if b < 0x80 else (b - 0x100) for b in bytes[16:20]]
        return icao, lat, lon, alt, vs, stealth, typ, ns, ew

    def general_work(self, input_items, output_items):
        # Wait until we get at least one packet worth of Manchester bits
        if len(input_items[0]) < 464:
            self.consume(0, 0)
            return 0

        index = input_items[0].tostring().find(self.sync_word, 0, -464+48)
        while index != -1:
            self.manchester_demod_packet(input_items[0][index:index+464])
            index = input_items[0].tostring().find(self.sync_word, index+464, -464+48)

        self.consume(0, len(input_items[0])-463)
        return 0
