from struct import pack, unpack, calcsize

BLOCK_COUNT = 0x10
BLOCK_LENGTH = 0x2000
BLOCK_HEADER_LENGTH = 0x80

CHAINED_BLOCK_NUMBER_OFFSET = 0x8
PRODUCT_CODE_OFFSET = 0xc
PRODUCT_CODE_LENGTH = 0xa
GAME_CODE_OFFSET = 0x16

PSX_DIRECTORY_USED = 0x50
PSX_BLOCK_TOP = 0x01
PSX_BLOCK_LINK = 0x02

class PS1Card(object):
  def __init__(self, device):
    self._device = device

  def _seekToBlock(self, block_number):
    assert 0 <= block_number < BLOCK_COUNT, hex(block_number)
    self._device.seek(block_number * BLOCK_LENGTH)

  def _seekToBlockHeader(self, block_number):
    assert 0 <= block_number < BLOCK_COUNT, hex(block_number)
    self._device.seek(block_number * BLOCK_HEADER_LENGTH)

  def readBlockHeader(self, block_number):
    self._seekToBlockHeader(block_number)
    return self._device.read(BLOCK_HEADER_LENGTH)

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

  def iterSaveList(self):
    superblock = self.readBlock(0)
    for block_number in xrange(1, BLOCK_COUNT):
      header_start = BLOCK_HEADER_LENGTH * block_number
      block_state = ord(superblock[header_start])
      if block_state & PSX_DIRECTORY_USED \
        and not (block_state & PSX_BLOCK_LINK):
        yield PS1Save(self, block_number)

class PS1Save(object):

  def __init__(self, card, first_block_number):
    self._card = card
    block_list = [first_block_number]
    append = block_list.append
    self._block_list = block_list
    block_number = first_block_number
    block_header = card.readBlockHeader(first_block_number)
    self._product_code = block_header[PRODUCT_CODE_OFFSET: \
      PRODUCT_CODE_OFFSET + PRODUCT_CODE_LENGTH]
    self._game_code = block_header[GAME_CODE_OFFSET:]
    while True:
      raw_number = block_header[CHAINED_BLOCK_NUMBER_OFFSET: \
        CHAINED_BLOCK_NUMBER_OFFSET + 2]
      if raw_number == '\xff\xff':
        break
      block_number = unpack('<h', raw_number)[0] + 1
      block_header = card.readBlockHeader(block_number)
      append(block_number)

  def getId(self):
    return str(self._block_list[0])


