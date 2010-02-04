"""
Some rules for this description:
 - Individual bytes are displayed in file order (file offset increases when
   reading to the right).
 - Numbers are in decimal unless prefixed by '0x'
 - Strings are ASCII representations of bytes

PS1 Memory Card structure
  16 * 8kB blocks
  First block: block allocation table
  Other blocks: Data

Block allocation table structure:
  16 * 128B entries (one per block, in same order)
  Last byte of each entry is a XOR checksum of entry's bytes.
  First entry starts with 0x4D 0x43 ("MC") and is filled with zeros.
  Other entries scruture (offset, length):
    0x0, 1: Block content
      From LSb to MSb
      Bit 0:
        0: Intermediate link block
        1: Linked block list start or end (bit 1 must be 1)
      Bit 1:
        0: Single block or first block of a linked list
        1: Linked block
      Bits 4..7:
        0x5: Block used
        0xA: Block free
    0x4, 4: Save size
      Integer, LSB first
    0x8, 2: Next linked block
      Integer, LSB first
      0xffff means "no next block".
      Beware: The first allocation entry is not numbered, so first save block
      is block 0, not 1.
    0xa, 1: ?
      0x42 ("B')
    0xb, 1: Game region
      0x41 ("A"): America (SCEA)
      0x45 ("E"): Europe (SCEE)
      0x49 ("I"): Japan (SCEI)
    0xc, 10: Product code
    0x10, 8: Save identifier
"""
from struct import pack, unpack, calcsize
import mmap

SUPERBLOCK_MAGIC = 'MC'

BLOCK_COUNT = 0x10
BLOCK_LENGTH = 0x2000
BLOCK_HEADER_LENGTH = 0x80
BLOCK_HEADER_AREA_LENGTH = BLOCK_HEADER_LENGTH * BLOCK_COUNT
XOR_OFFSET = BLOCK_HEADER_LENGTH - 1

BLOCK_STATUS_FREE = 0xA0
BLOCK_STATUS_USED = 0x50
BLOCK_STATUS_LINKED = 0x02
BLOCK_STATUS_END = 0x01
SAVE_LENGTH_OFFSET = 0x4
SAVE_LENGTH_FORMAT = '<I'
SAVE_LENGTH_LENGTH = 4
assert calcsize(SAVE_LENGTH_FORMAT) == SAVE_LENGTH_LENGTH
CHAINED_BLOCK_NUMBER_OFFSET = 0x8
CHAINED_BLOCK_NUMBER_FORMAT = '<H'
CHAINED_BLOCK_NUMBER_LENGTH = 2
CHAINED_BLOCK_VALUE_NONE = 0xffff
assert calcsize(CHAINED_BLOCK_NUMBER_FORMAT) == CHAINED_BLOCK_NUMBER_LENGTH
UNKNOWN_OFFSET_1 = 0xa
UNKNOWN_OFFSET_1_VALUE = 'B'
REGION_CODE_OFFSET = 0xb
REGION_CODE_LENGTH = 1
PRODUCT_CODE_OFFSET = 0xc
PRODUCT_CODE_LENGTH = 10
GAME_CODE_OFFSET = 0x10
GAME_CODE_LENGTH = 8

class PS1Card(object):
    _device = None
    _link_map = None

    def __init__(self, device):
        # Keep a reference to received file object se it doesn't get
        # garbage-collected while we might still want to access its mmaped
        # version.
        self._raw_device = device
        # On the contrary of what is advertised by python mmap module
        # documentation, providing a 0 length to mmap won't map the whole file.
        device.seek(0, 2)
        self._device = mmap.mmap(device.fileno(), device.tell())
        assert self.read(len(SUPERBLOCK_MAGIC), 0) == SUPERBLOCK_MAGIC

    def __del__(self):
        if self._device is not None:
            self._device.flush()

    def updateXOR(self, block_number):
        offset = block_number * BLOCK_HEADER_LENGTH
        computed_xor = 0
        for byte in self.read(BLOCK_HEADER_LENGTH - 1, offset):
            computed_xor ^= ord(byte)
        self.write(chr(computed_xor), offset + BLOCK_HEADER_LENGTH - 1)

    def checkXOR(self, block_number):
        offset = block_number * BLOCK_HEADER_LENGTH
        computed_xor = 0
        for byte in self.read(BLOCK_HEADER_LENGTH, offset):
            computed_xor ^= ord(byte)
        if computed_xor:
            raise ValueError, 'Header %i corrupted' % (block_number, )

    def iterChainedBlocks(self, block_number):
        checkXOR = self.checkXOR
        while True:
            checkXOR(block_number)
            offset = block_number * BLOCK_HEADER_LENGTH + \
                CHAINED_BLOCK_NUMBER_OFFSET
            block_number = unpack(CHAINED_BLOCK_NUMBER_FORMAT, \
                self.read(CHAINED_BLOCK_NUMBER_LENGTH, offset))[0]
            if block_number == CHAINED_BLOCK_VALUE_NONE:
                break
            block_number += 1
            yield block_number

    def getBlockLinkMap(self):
        link_map = self._link_map
        if link_map is None:
            link_map = {}
            for block_number in xrange(1, BLOCK_COUNT):
                if block_number not in link_map:
                    self.checkXOR(block_number)
                    block_state = ord(self.read(1, block_number * \
                        BLOCK_HEADER_LENGTH))
                    if block_state & BLOCK_STATUS_USED == BLOCK_STATUS_USED:
                        if block_state & BLOCK_STATUS_LINKED:
                            link_map[block_number] = -1
                        else:
                            link_map[block_number] = block_number
                            for chained_block_number in self.iterChainedBlocks(
                                block_number):
                                link_map[chained_block_number] = block_number
            self._link_map = link_map
        return link_map.copy()

    def getSave(self, block_number):
        base_block_number = self.getBlockLinkMap().get(block_number)
        if base_block_number is None:
            result = None
        else:
            result = PS1Save(self, base_block_number)
        return result

    def createSave(self, block_number):
        self._allocateBlock(block_number, True)

    def _allocateBlock(self, block_number, is_head):
        """
          If block is free, mark it as used and erase content.
        """
        self.checkXOR(block_number)
        offset = block_number * BLOCK_HEADER_LENGTH
        if ord(self.read(1, offset)) & BLOCK_STATUS_USED == 0:
            write = self.write
            # Mark as used
            write(chr(BLOCK_STATUS_USED | BLOCK_STATUS_END), offset)
            if is_head:
                # Initialise save length to 1 block
                write(pack(SAVE_LENGTH_FORMAT, BLOCK_LENGTH),
                    offset + SAVE_LENGTH_OFFSET)
                # Set unknown value 1
                write(UNKNOWN_OFFSET_1_VALUE, UNKNOWN_OFFSET_1)
            # Mark there is no next block
            write(pack(CHAINED_BLOCK_NUMBER_FORMAT, CHAINED_BLOCK_VALUE_NONE),
                offset + CHAINED_BLOCK_NUMBER_OFFSET)
            # we're done editing header, compute XOR
            self.updateXOR(block_number)
        else:
            raise ValueError, 'Block %i already allocated' % (block_number, )

    def _chainBlocks(self, first_block_number, second_block_number):
        write(pack(CHAINED_BLOCK_NUMBER_FORMAT, second_block_number),
          first_block_number * BLOCK_HEADER_LENGTH + \
          CHAINED_BLOCK_NUMBER_OFFSET)

    def _getSaveBlockCount(self, block_number):
        size_offset = block_number * BLOCK_HEADER_LENGTH + SAVE_LENGTH_OFFSET
        current_size = unpack(SAVE_LENGTH_FORMAT,
            self.read(SAVE_LENGTH_LENGTH, size_offset))[0]
        assert current_size % BLOCK_LENGTH == 0, current_size
        return current_size / BLOCK_LENGTH

    def _setSaveBlockCount(self, block_number, block_count):
        size_offset = block_number * BLOCK_HEADER_LENGTH + SAVE_LENGTH_OFFSET
        self.write(pack(SAVE_LENGTH_FORMAT, block_count * BLOCK_LENGTH),
            size_offset)

    def appendBlock(self, head_block_number, new_block_number):
        self._allocateBlock(new_block_number, False)
        last_block_number = head_block_number
        for last_block_number in self.iterChainedBlocks(head_block_number):
            pass
        self._chainBlocks(last_block_number, new_block_number)
        if last_block_number != head_block_number:
            self.updateXOR(last_block_number)
        self._setSaveBlockCount(head_block_number,
            self._getSaveBlockCount(head_block_number) + 1)
        self.updateXOR(head_block_number)

    def freeBlock(self, block_number):
        offset = block_number * BLOCK_HEADER_LENGTH
        block_state = ord(self.read(1, offset))
        self.write(chr((block_state & 0xf) | BLOCK_STATUS_FREE), offset)
        self.updateXOR(block_number)

    def deleteSave(self, block_number):
        """
          If block is used and not a linked block, mark it as free.
          If it links to other blocks, mark them as free aswell.
          No data is actualy erased.
        """
        offset = block_number * BLOCK_HEADER_LENGTH
        if ord(self.read(1, offset)) & BLOCK_STATUS_USED == BLOCK_STATUS_USED:
            for linked_block_number in self.iterChainedBlocks(block_number):
                self.freeBlock(linked_block_number)
            self.freeBlock(block_number)
        else:
            raise ValueError, 'Block %i already free' % (block_number, )

    def write(self, buf, offset):
        if offset < BLOCK_HEADER_AREA_LENGTH:
            # Invalidate cached link map when writing in a block header
            self._link_map = None
        self._device[offset:offset + len(buf)] = buf

    def read(self, size, offset):
        return self._device[offset:offset + size]

class PS1Save(object):
    def __init__(self, card, first_block_number):
        self._card = card
        block_list = [first_block_number]
        append = block_list.append
        self._block_list = block_list
        block_number = first_block_number
        block_header = card.read(BLOCK_HEADER_LENGTH,
            first_block_number * BLOCK_HEADER_LENGTH)
        self._region = block_header[REGION_CODE_OFFSET: \
            REGION_CODE_OFFSET + REGION_CODE_LENGTH]
        self._product_code = block_header[PRODUCT_CODE_OFFSET: \
            PRODUCT_CODE_OFFSET + PRODUCT_CODE_LENGTH]
        self._game_code = block_header[GAME_CODE_OFFSET: \
            GAME_CODE_OFFSET + GAME_CODE_LENGTH]
        save_length = unpack(SAVE_LENGTH_FORMAT, block_header[ \
            SAVE_LENGTH_OFFSET:SAVE_LENGTH_OFFSET + SAVE_LENGTH_LENGTH])[0]
        for block_number in card.iterChainedBlocks(first_block_number):
            append(block_number)
        assert save_length == self.getDataSize()

    def readHeader(self, name, size, offset):
        entry_size = self.getEntrySize(name)
        if offset < entry_size:
            base_offset = self._block_list[0] * BLOCK_LENGTH
            result = self._card.read(min(size, entry_size - offset),
                self.getEntryOffset(name) + offset + base_offset)
        else:
            result = ''
        return result

    def writeHeader(self, name, buf, offset):
        entry_size = self.getEntrySize(name)
        if offset < entry_size:
            card = self._card
            block_number = self._block_list[0]
            base_offset = block_number * BLOCK_LENGTH
            result = entry_size - offset
            card.write(buf[:result],
              self.getEntryOffset(name) + offset + base_offset)
            card.updateXOR(block_number)
        else:
            result = 0
        return result

    def readData(self, size, offset):
        data_size = self.getDataSize()
        result = []
        if offset < data_size:
            append = result.append
            block_list = self._block_list
            read = self._card.read
            size = min(size, data_size - offset)
            while size:
                block_id, block_offset = divmod(offset, BLOCK_LENGTH)
                to_read = BLOCK_LENGTH - block_offset
                append(read(to_read,
                  block_list[block_id] * BLOCK_LENGTH + block_offset))
                size -= to_read
                offset += to_read
        return ''.join(result)

    def writeData(self, buf, offset):
        data_size = self.getDataSize()
        if offset >= data_size:
            raise ValueError, 'Writing past end of file'
        written = 0
        block_list = self._block_list
        block_count = len(block_list)
        write = self._card.write
        while buf:
            block_id, block_offset = divmod(offset + written, BLOCK_LENGTH)
            if block_id >= block_count:
                break
            to_write = min(len(buf), BLOCK_LENGTH - block_offset)
            data_to_write, buf = buf[:to_write], buf[to_write:]
            write(data_to_write, block_list[block_id] * BLOCK_LENGTH + \
                block_offset)
            written += to_write
        return written

    def read(self, name, size, offset):
        if name == SAVE_DATA_ENTRY_ID:
            result = self.readData(size, offset)
        else:
            result = self.readHeader(name, size, offset)
        return result

    def write(self, name, buf, offset):
        if name == SAVE_DATA_ENTRY_ID:
            result = self.writeData(buf, offset)
        else:
            result = self.writeHeader(name, buf, offset)
        return result

    def iterEntries(self):
        for entry in SAVE_ENTRY_DICT.iterkeys():
            yield entry

    def hasEntry(self, name):
        return name in SAVE_ENTRY_DICT

    def getEntryOffset(self, name):
        return SAVE_ENTRY_DICT[name]['offset']

    def getEntrySize(self, name):
        if name == SAVE_DATA_ENTRY_ID:
            result = self.getDataSize()
        else:
            result = SAVE_ENTRY_DICT[name]['size']
        return result

    def getDataSize(self):
        return len(self._block_list) * BLOCK_LENGTH

SAVE_DATA_ENTRY_ID = 'data'

SAVE_ENTRY_DICT = {
    SAVE_DATA_ENTRY_ID: None,
    'game_code': {
        'offset': GAME_CODE_OFFSET,
        'size': GAME_CODE_LENGTH,
    },
    'product_code': {
        'offset': PRODUCT_CODE_OFFSET,
        'size': PRODUCT_CODE_LENGTH,
    },
    'region': {
        'offset': REGION_CODE_OFFSET,
        'size': REGION_CODE_LENGTH,
    },
}

