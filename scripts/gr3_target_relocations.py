"""Collect typed firmware references while generating the private ARM image.

Only compiler mapping symbols and explicit assembler/table emitters introduce
records. Image assets are never scanned as code or pointers. Records are an
input to target verification, not evidence that a target is compatible.
"""
import struct


def firmware_address(value):
    return 0x53000000 <= value < 0x540b5740 or 0x55000000 <= value < 0x56000000


def immediate(word):
    return ((word >> 4) & 0xf000) | (word & 0xfff)


class Relocations:
    def __init__(self):
        self.records = {}
        self.typed_words = {}

    def add(self, kind, sites, words, target):
        if firmware_address(target):
            self.records[tuple(sites)] = dict(kind=kind, sites=list(sites), words=list(words), target=target)

    def data(self, base, raw):
        for off in range(0,len(raw)-3,4):
            word = struct.unpack_from('<I',raw,off)[0]
            self.typed_words[base+off]=('data',word)
            self.add('pointer',[base+off],[word],word)

    def code(self, base, raw):
        lows = {}
        for off in range(0,len(raw)-3,4):
            word = struct.unpack_from('<I',raw,off)[0]
            site = base+off
            self.typed_words[site]=('code',word)
            if word & 0x0e000000 == 0x0a000000 and word >> 28 != 15:
                delta = (word & 0xffffff)*4
                if delta & 0x2000000: delta -= 0x4000000
                self.add('branch',[site],[word],site+8+delta)
                # Pairs must be within one straight-line sequence.
                lows.clear()
            elif word & 0x0ff00000 == 0x03000000:
                lows[(word >> 12)&15] = (site,word)
            elif word & 0x0ff00000 == 0x03400000:
                reg = (word >> 12)&15
                if reg in lows:
                    lo,low = lows.pop(reg)
                    if low >> 28 == word >> 28:
                        self.add('mov_pair',[lo,site],[low,word],immediate(low)|(immediate(word)<<16))
            else:
                # ARM data processing and loads write Rd. Stores, compares,
                # pushes and coprocessor instructions cannot define a pair.
                category = (word >> 25)&7
                if category in (0,1):
                    opcode = (word >> 21)&15
                    if opcode not in (8,9,10,11): lows.pop((word >> 12)&15,None)
                elif category in (2,3) and word & (1<<20):
                    lows.pop((word >> 12)&15,None)

    def elf(self, elf, starts, image):
        """Use ELF $a/$d symbols, including literal pools inside .text."""
        shoff = struct.unpack_from('<I',elf,32)[0]
        size,count = struct.unpack_from('<HH',elf,46)
        sections = [struct.unpack_from('<10I',elf,shoff+i*size) for i in range(count)]
        mappings = {}
        for row in sections:
            if row[1] != 2: continue
            strings = sections[row[6]]
            names = elf[strings[4]:strings[4]+strings[5]]
            for at in range(row[4],row[4]+row[5],16):
                name,value,_,_,_,section = struct.unpack_from('<IIIBBH',elf,at)
                label = names[name:].split(b'\0',1)[0]
                if section in starts and label.startswith((b'$a',b'$d',b'$t')):
                    mappings.setdefault(section,[]).append((value-sections[section][3],label[:2]))
        origin = min(starts.values())
        for section,rows in mappings.items():
            rows.sort()
            for i,(offset,kind) in enumerate(rows):
                end = rows[i+1][0] if i+1<len(rows) else sections[section][5]
                address = starts[section]+offset
                data = image[address-origin:starts[section]+end-origin]
                if kind == b'$a': self.code(address,data)
                elif kind == b'$d': self.data(address,data)
                else: raise ValueError('Thumb code is not supported by GR III target relocation')

    def linked(self, elf):
        shoff = struct.unpack_from('<I',elf,32)[0]
        size,count = struct.unpack_from('<HH',elf,46)
        rows = [struct.unpack_from('<10I',elf,shoff+i*size) for i in range(count)]
        starts = {i:r[3] for i,r in enumerate(rows) if r[2]&2 and r[5]}
        if not starts: return
        base = min(starts.values())
        raw = bytearray(max(starts[i]+rows[i][5] for i in starts)-base)
        for i,start in starts.items():
            row=rows[i];raw[start-base:start-base+row[5]]=elf[row[4]:row[4]+row[5]]
        self.elf(elf,starts,raw)

    def finish(self, base, raw):
        result = []
        for record in self.records.values():
            if all(base<=site and site+4<=base+len(raw) and
                   struct.unpack_from('<I',raw,site-base)[0]==word
                   for site,word in zip(record['sites'],record['words'])):
                result.append(record)
        return sorted(result,key=lambda row:(row['sites'][0],row['kind']))

    def coverage(self,base,raw):
        ranges=[]
        for site,(kind,word) in sorted(self.typed_words.items()):
            if not(base<=site and site+4<=base+len(raw)) or struct.unpack_from('<I',raw,site-base)[0]!=word:continue
            if ranges and ranges[-1]['kind']==kind and ranges[-1]['end']==site:ranges[-1]['end']+=4
            else:ranges.append(dict(start=site,end=site+4,kind=kind))
        return ranges


relocations = Relocations()
