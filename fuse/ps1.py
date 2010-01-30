from struct import pack, unpack, calcsize

BLOCK_COUNT = 0x10
BLOCK_LENGTH = 0x2000
BLOCK_HEADER_LENGTH = 0x80

CHAINED_BLOCK_NUMBER_OFFSET = 0x8
PRODUCT_CODE_OFFSET = 0xc
PRODUCT_CODE_LENGTH = 0xa
GAME_CODE_OFFSET = 0x16

SAVE_TITLE_OFFSET = 0x4
SAVE_TITLE_LENGTH = 0x5c # XXX: is it true ?
TITLE_CHAR_DICT = {
  0x8144: '.',
  0x8146: ':',
  0x8168: '"',
  0x8169: '(',
  0x816A: ')',
  0x816D: '[',
  0x816E: ']',
  0x817C: '-',
  0x8293: '%',
  0x8295: '&',
}
PALETTE_OFFSET = 0x60
PALETTE_ENTRY_FORMAT = '>h'
PALETTE_ENTRY_LEN = calcsize(PALETTE_ENTRY_FORMAT)
PALETTE_ENTRY_COUNT = 0xf
IMAGE_COUNT_OFFSET = 0x2
IMAGE_COUNT_MASK = 0x3
IMAGE_OFFSET = 0x80
IMAGE_LENGTH = 0x80

PSX_DIRECTORY_FREE = 0xA0
PSX_DIRECTORY_USED = 0x50
PSX_BLOCK_TOP = 0x01
PSX_BLOCK_LINK = 0x02
PSX_BLOCK_LINK_END = 0x03

class PS1Card(object):
  def __init__(self, device):
    self._device = device

  def _seekToBlock(self, block_number):
    assert 0 < block_number < BLOCK_COUNT, hex(block_number)
    self._device.seek(block_number * BLOCK_LENGTH)

  def _seekToBlockHeader(self, block_number):
    assert 0 < block_number < BLOCK_COUNT, hex(block_number)
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
  _title = None
  _icon = None

  def __init__(self, card, first_block_number):
    self._card = card
    block_list = [first_block_number]
    block_list.append
    self._block_list = block_list
    block_number = first_block_number
    block_header = card.readBlockHeader(first_block_number)
    self._product_code = block_header[PRODUCT_CODE_OFFSET: \
      PRODUCT_CODE_OFFSET + PRODUCT_CODE_LENGTH]
    self._game_code = block_header[GAME_CODE_OFFSET:]
    while True:
      block_state = ord(block_header[0])
      if block_state & PSX_BLOCK_LINK_END == PSX_BLOCK_LINK:
        block_number = ord(block_header[CHAINED_BLOCK_NUMBER_OFFSET])
        block_header = card.readBlockHeader(block_number)
        append(block_number)
      else:
        break

  def getId(self):
    return str(self._block_list[0])

  def getTitle(self):
    title = self._title
    if title is None:
      encoded_title = self._card.readBlock(self._block_list[0])[ \
        SAVE_TITLE_OFFSET:SAVE_TITLE_OFFSET + SAVE_TITLE_LEN]
      char_list = []
      append = char_list.append
      for char_index in xrange(0, SAVE_TITLE_LENGTH, 2):
        encoded_char = encoded_title[char_index:char_index + 2]
        if char == '\x00':
          break
        append(encoded_char)
      title = ''.join(char_list).decode('shift_jis')
      self._title = title
    return title

  def getIconList(self):
    icon = self._icon
    if icon is None:
      block = self._card.readBlock(self._block_list[0])
      palette = []
      append = palette.append
      for x in xrange(PALETTE_ENTRY_COUNT):
        palette_bgr_value = unpack(PALETTE_ENTRY_FORMAT,
          block[PALETTE_OFFSET + x * PALETTE_ENTRY_LENGTH])[0]
        r_value = (palette_bgr_value & 0x1f) * 8
        g_value = (palette_bgr_value >> 5 & 0x1f) * 8
        b_value = (palette_bgr_value >> 10 & 0x1f) * 8
        append((r_value << 16) | (g_value << 8) | b_value)
      icon = []
      for icon_id in xrange(ord(block[IMAGE_COUNT_OFFSET]) & IMAGE_COUNT_MASK):
        icon_frame = []
        append = icon_frame.append
        icon_offset = IMAGE_OFFSET + IMAGE_LENGTH * icon_id
        for pixel_pair in block[icon_offset:icon_offset + IMAGE_LENGTH]:
          append(palette[pixel_pair >> 4])
          append(palette[pixel_pair & 0xf])
        icon.append(icon_frame)
    return icon

