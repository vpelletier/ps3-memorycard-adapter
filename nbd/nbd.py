from struct import pack, unpack, calcsize

NBD_GREETING_PREFIX = 'NBDMAGIC\x00\x00\x42\x02\x81\x86\x12\x53'
NBD_GREETING_SUFFIX = '\0' * 124

NBD_REQUEST_FORMAT = '>L8sQL'
NBD_REQUEST_LEN = calcsize(NBD_REQUEST_FORMAT)
NBD_REQUEST_MAGIC = '\x25\x60\x95\x13'
NBD_REQUEST_MAGIC_LEN = len(NBD_REQUEST_MAGIC)

NBD_ACTION_READ = 0
NBD_ACTION_WRITE = 1
NBD_ACTION_DISCONNECT = 2

NBD_RESPONSE_FORMAT = '>L8s'
NBD_RESPONSE_MAGIC = '\x67\x44\x66\x98'

ERROR_BAD_MAGIC = 1
ERROR_NOT_IMPLEMENTED = 2
ERROR_SHORT_READ = 3
ERROR_OTHER = 4

NBD_FLAG_HAS_FLAGS = 1
NBD_FLAG_READ_ONLY = 1 << 1

def answer(sock, handle, error=0, data=''):
  sock.sendall(NBD_RESPONSE_MAGIC + pack(NBD_RESPONSE_FORMAT, error, handle))
  if data:
    sock.sendall(data)

class NBDServer(object):
  def __init__(self, device):
    self._device = device
    self._size = device.getSize()

  def greet(self, sock, read_only=False):
    sock.sendall(NBD_GREETING_PREFIX)
    flags = NBD_FLAG_HAS_FLAGS
    if read_only:
      flags |= NBD_FLAG_READ_ONLY
    sock.sendall(pack('>Qi', self._size, flags))
    sock.sendall(NBD_GREETING_SUFFIX)

  def handle(self, sock):
    """
      Return values:
        True: operation can continue on socket
        False: socket must be closed
      When this method raises, the 
    """
    result = True
    magic = sock.recv(NBD_REQUEST_MAGIC_LEN)
    if magic != NBD_REQUEST_MAGIC:
      return False
    request = sock.recv(NBD_REQUEST_LEN)
    if len(request) != NBD_REQUEST_LEN:
      import pdb; pdb.set_trace()
    (action, handle, offset, length) = unpack(
      NBD_REQUEST_FORMAT, request)
    if action == NBD_ACTION_WRITE:
      print 'NBD: write 0x%x bytes at 0x%x' % (length, offset)
      data = sock.recv(length)
      if len(data) != length:
        result = False
      else:
        try:
          self._device.write(offset, data)
        except:
          answer(sock, handle, error=ERROR_OTHER)
          raise
        answer(sock, handle)
    elif action == NBD_ACTION_READ:
      print 'NBD: read 0x%x bytes at 0x%x' % (length, offset)
      try:
        data = self._device.read(offset, length)
      except:
        answer(sock, handle, error=ERROR_OTHER)
        raise
      if len(data) != length:
        import pdb; pdb.set_trace()
        answer(sock, handle, error=ERROR_SHORT_READ)
        result = False
      answer(sock, handle, data=data)
    elif action == NBD_ACTION_DISCONNECT:
      print 'NBD: disconnect'
      result = False
    else:
      answer(sock, handle, error=ERROR_NOT_IMPLEMENTED)
      result = False
    return result

