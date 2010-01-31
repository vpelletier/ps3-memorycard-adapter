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
ERROR_READ_ONLY = 4
ERROR_OTHER = 5

NBD_FLAG_HAS_FLAGS = 1
NBD_FLAG_READ_ONLY = 1 << 1

def answer(sock, handle, error=0, data=''):
  sock.sendall(NBD_RESPONSE_MAGIC + pack(NBD_RESPONSE_FORMAT, error, handle))
  if data:
    sock.sendall(data)

class NBDServer(object):
  """
    Python implementation of MBD protocol.

    Socket handling & event loop must be done outside of this class.
  """

  def __init__(self, device):
    """
      device
        Instance implementing the following methods:
          getSize() -> int
            Size of the underlying storage.
          write(offset, data)
            Write <data> starting at <offset>.
          read(offset, length) -> string
            Read <length> bytes starting at <offset>.
    """
    self._device = device
    self._size = device.getSize()

  def greet(self, sock, read_only=False):
    """
      To be called upon socket connection establishment.
      Sends NBD server greeting sequence, device size, and whether it is
      read-only.

      read_only (bool)
        Whether the device should be advertised as allowing writes.
        This is enforced withing this class, so that a client ignoring this
        information will be refused to write anyway.
    """
    sock.sendall(NBD_GREETING_PREFIX)
    flags = NBD_FLAG_HAS_FLAGS
    if read_only:
      flags |= NBD_FLAG_READ_ONLY
    self._read_only = read_only
    sock.sendall(pack('>Qi', self._size, flags))
    sock.sendall(NBD_GREETING_SUFFIX)

  def handle(self, sock):
    """
      To be called upon incomming data on socket.
      Blocks until an entire command has been received, and response had been
      sent back.

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
      return False
    (action, handle, offset, length) = unpack(
      NBD_REQUEST_FORMAT, request)
    if action == NBD_ACTION_WRITE:
      data = sock.recv(length)
      if len(data) != length:
        result = False
      elif self._read_only:
        answer(sock, handle, error=ERROR_READ_ONLY)
      else:
        try:
          self._device.write(offset, data)
        except:
          answer(sock, handle, error=ERROR_OTHER)
          raise
        answer(sock, handle)
    elif action == NBD_ACTION_READ:
      try:
        data = self._device.read(offset, length)
      except:
        answer(sock, handle, error=ERROR_OTHER)
        raise
      if len(data) != length:
        answer(sock, handle, error=ERROR_SHORT_READ)
        result = False
      answer(sock, handle, data=data)
    elif action == NBD_ACTION_DISCONNECT:
      result = False
    else:
      answer(sock, handle, error=ERROR_NOT_IMPLEMENTED)
      result = False
    return result

