from struct import pack, unpack, calcsize

BLOCK_COUNT = 0x10
BLOCK_LENGTH = 0x2000
BLOCK_HEADER_LENGTH = 0x80

CHAINED_BLOCK_NUMBER_OFFSET = 0x8
PRODUCT_CODE_OFFSET = 0xc
PRODUCT_CODE_LENGTH = 0xa
GAME_CODE_OFFSET = 0x16
GAME_CODE_LENGTH = 8 # XXX: is it true ?

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

  def _isSaveHead(self, block_number):
    superblock = self.readBlock(0)
    header_start = BLOCK_HEADER_LENGTH * block_number
    block_state = ord(superblock[header_start])
    return block_state & PSX_DIRECTORY_USED \
      and not (block_state & PSX_BLOCK_LINK)

  def iterSaveIdList(self):
    for block_number in xrange(1, BLOCK_COUNT):
      if self._isSaveHead(block_number):
        yield block_number

  def getSave(self, block_number):
    if self._isSaveHead(block_number):
      result = PS1Save(self, block_number)
    else:
      result = None
    return result

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
    self._game_code = block_header[GAME_CODE_OFFSET: \
      GAME_CODE_OFFSET + GAME_CODE_LENGTH]
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

  def hasEntry(seld, name):
    return name in SAVE_ENTRY_DICT

  def getEntrySize(self, name):
     if name in SAVE_ENTRY_DICT:
       size = SAVE_ENTRY_DICT[name]['size']
       if callable(size):
         size = size(self)
     else:
       size = None
     return size

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
    'size': lambda x: len(x._block_list) * BLOCK_LENGTH,
  },
}

