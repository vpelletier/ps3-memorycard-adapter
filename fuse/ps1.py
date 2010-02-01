from struct import pack, unpack, calcsize

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

SUPERBLOCK_MAGIC = 'MC'

BLOCK_COUNT = 0x10
BLOCK_LENGTH = 0x2000
BLOCK_HEADER_LENGTH = 0x80
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
CHAINED_BLOCK_NUMBER_FORMAT = '<h'
CHAINED_BLOCK_NUMBER_LENGTH = 2
assert calcsize(CHAINED_BLOCK_NUMBER_FORMAT) == CHAINED_BLOCK_NUMBER_LENGTH
REGION_CODE_OFFSET = 0xb
REGION_CODE_LENGTH = 1
PRODUCT_CODE_OFFSET = 0xc
PRODUCT_CODE_LENGTH = 10
GAME_CODE_OFFSET = 0x10
GAME_CODE_LENGTH = 8

class PS1Card(object):
  def __init__(self, device):
    self._device = device
    superblock = self.readBlockHeader(0)
    assert superblock[:len(SUPERBLOCK_MAGIC)] == SUPERBLOCK_MAGIC

  def _seekToBlock(self, block_number):
    assert 0 <= block_number < BLOCK_COUNT, hex(block_number)
    self._device.seek(block_number * BLOCK_LENGTH)

  def _seekToBlockHeader(self, block_number):
    assert 0 <= block_number < BLOCK_COUNT, hex(block_number)
    self._device.seek(block_number * BLOCK_HEADER_LENGTH)

  def readBlockHeader(self, block_number):
    self._seekToBlockHeader(block_number)
    header = self._device.read(BLOCK_HEADER_LENGTH)
    # Check header consistency
    computed_xor = 0
    for byte in header:
      computed_xor ^= ord(byte)
    if computed_xor:
      raise ValueError, 'Header %i corrupted' % (block_number, )
    return header

  def writeBlockHeader(self, block_number, data):
    assert len(data) == BLOCK_HEADER_LENGTH, hex(len(data))
    self._seekToBlockHeader(block_number)
    self._device.write(data)

  def readBlock(self, block_number):
    self._seekToBlock(block_number)
    return self._device.read(BLOCK_LENGTH)

  def writeBlock(self, block_number, data):
    assert len(data) == BLOCK_LENGTH, hex(len(data))
    self._seekToBlock(block_number)
    self._device.write(data)

  def _isSaveHead(self, block_number):
    superblock = self.readBlock(0)
    header_start = BLOCK_HEADER_LENGTH * block_number
    block_state = ord(superblock[header_start])
    return block_state & BLOCK_STATUS_USED == BLOCK_STATUS_USED \
      and block_state & BLOCK_STATUS_LINKED == 0

  def iterSaveIdList(self):
    for block_number in xrange(1, BLOCK_COUNT):
      if self._isSaveHead(block_number):
        yield block_number

  def iterChainedBlocks(self, block_number):
    while True:
      block_header = self.readBlockHeader(block_number)
      raw_number = block_header[CHAINED_BLOCK_NUMBER_OFFSET: \
        CHAINED_BLOCK_NUMBER_OFFSET + CHAINED_BLOCK_NUMBER_LENGTH]
      if raw_number == '\xff\xff':
        break
      block_number = unpack(CHAINED_BLOCK_NUMBER_FORMAT, raw_number)[0] + 1
      block_header = self.readBlockHeader(block_number)
      yield block_number

  def getBlockLinkMap(self):
    link_map = {}
    for block_number in xrange(1, BLOCK_COUNT):
      if block_number not in link_map and self._isSaveHead(block_number):
        link_map[block_number] = block_number
        for chained_block_number in self.iterChainedBlocks(block_number):
          link_map[chained_block_number] = block_number
    return link_map

  def getSave(self, block_number):
    base_block_number = self.getBlockLinkMap().get(block_number)
    if base_block_number is None:
      result = None
    else:
      result = PS1Save(self, base_block_number)
    return result

class PS1Save(object):
  def __init__(self, card, first_block_number):
    self._card = card
    block_list = [first_block_number]
    append = block_list.append
    self._block_list = block_list
    block_number = first_block_number
    block_header = card.readBlockHeader(first_block_number)
    self._region = block_header[REGION_CODE_OFFSET: \
      REGION_CODE_OFFSET + REGION_CODE_LENGTH]
    self._product_code = block_header[PRODUCT_CODE_OFFSET: \
      PRODUCT_CODE_OFFSET + PRODUCT_CODE_LENGTH]
    self._game_code = block_header[GAME_CODE_OFFSET: \
      GAME_CODE_OFFSET + GAME_CODE_LENGTH]
    save_length = unpack(SAVE_LENGTH_FORMAT, block_header[SAVE_LENGTH_OFFSET: \
      SAVE_LENGTH_OFFSET + SAVE_LENGTH_LENGTH])[0]
    for block_number in card.iterChainedBlocks(first_block_number):
      append(block_number)
    assert save_length == self.getDataLength()

  def getId(self):
    return str(self._block_list[0])

  def getGameCode(self):
    return self._game_code

  def getProductCode(self):
    return self._product_code

  def getData(self):
    result = []
    append = result.append
    for block_number in self._block_list:
      append(self._card.readBlock(block_number))
    return ''.join(result)

  def iterEntries(self):
    for entry in SAVE_ENTRY_DICT.iterkeys():
      yield entry

  def getEntry(self, name):
    if name in SAVE_ENTRY_DICT:
      return getattr(self, SAVE_ENTRY_DICT[name]['accessor'])()
    else:
      return None

  def hasEntry(self, name):
    return name in SAVE_ENTRY_DICT

  def getEntrySize(self, name):
     if name in SAVE_ENTRY_DICT:
       size = SAVE_ENTRY_DICT[name]['size']
       if callable(size):
         size = size(self)
     else:
       size = None
     return size

  def getDataLength(self):
    return len(self._block_list) * BLOCK_LENGTH

  def getRegion(self):
    return self._region

SAVE_ENTRY_DICT = {
  'game_code': {
    'accessor': 'getGameCode',
    'size': GAME_CODE_LENGTH,
  },
  'product_code': {
    'accessor': 'getProductCode',
    'size': PRODUCT_CODE_LENGTH,
  },
  'data': {
    'accessor': 'getData',
    'size': lambda x: x.getDataLength(),
  },
  'region': {
    'accessor': 'getRegion',
    'size': REGION_CODE_LENGTH,
  },
}

