import errno
import socket
import struct
from traceback import print_exc

NBD_GREETING_SUFFIX     = b'\0' * 124
NBD_GREETING_PREFIX     = b'NBDMAGICIHAVEOPT'
NBD_CLIENT_OPT_MAGIC    = b'IHAVEOPT'
NBD_SERVER_OPT_MAGIC    = b'\x00\x03\xe8\x89\x04\x55\x65\xa9'

NBD_REQUEST_FORMAT  = '>4sHH8sQL'
NBD_REQUEST_LEN     = struct.calcsize(NBD_REQUEST_FORMAT)
assert NBD_REQUEST_LEN == 28, NBD_REQUEST_LEN
NBD_REQUEST_MAGIC   = b'\x25\x60\x95\x13'

NBD_OPT_EXPORT_NAME         = 1
NBD_OPT_ABORT               = 2
NBD_OPT_LIST                = 3
NBD_OPT_PEEK_EXPORT         = 4
NBD_OPT_STARTTLS            = 5
NBD_OPT_INFO                = 6
NBD_OPT_GO                  = 7
NBD_OPT_STRUCTURED_REPLY    = 8
NBD_OPT_LIST_META_CONTEXT   = 9
NBD_OPT_SET_META_CONTEXT    = 10

NBD_REP_ACK                 = 1
NBD_REP_SERVER              = 2
NBD_REP_INFO                = 3
NBD_REP_META_CONTEXT        = 4
NBD_REP_ERR_UNSUP           = 2**31 + 1
NBD_REP_ERR_POLICY          = 2++31 + 2
NBD_REP_ERR_INVALID         = 2**31 + 3
NBD_REP_ERR_PLATFORM        = 2**31 + 4
NBD_REP_ERR_TLS_REQD        = 2**31 + 5
NBD_REP_ERR_UNKNOWN         = 2**31 + 6
NBD_REP_ERR_SHUTDOWN        = 2**31 + 7
NBD_REP_ERR_BLOCK_SIZE_REQD = 2**31 + 8
NBD_REP_ERR_TOO_BIG         = 2**31 + 9

NBD_CMD_READ            = 0
NBD_CMD_WRITE           = 1
NBD_CMD_DISC            = 2
NBD_CMD_FLUSH           = 3
NBD_CMD_TRIM            = 4
NBD_CMD_CACHE           = 5
NBD_CMD_WRITE_ZEROES    = 6
NBD_CMD_BLOCK_STATUS    = 7
NBD_CMD_RESIZE          = 8

NBD_CMD_FLAG_FUA        = 1 << 0
NBD_CMD_FLAG_NO_HOLE    = 1 << 1
NBD_CMD_FLAG_DF         = 1 << 2
NBD_CMD_FLAG_REQ_ONE    = 1 << 3
NBD_CMD_FLAG_FAST_ZERO  = 1 << 4
NBD_CMD_FLAG_UNKNOWN_MASK = (2**16 - 1) ^ (
    NBD_CMD_FLAG_FUA |
    NBD_CMD_FLAG_NO_HOLE |
    NBD_CMD_FLAG_DF |
    NBD_CMD_FLAG_REQ_ONE |
    NBD_CMD_FLAG_FAST_ZERO
)

NBD_REPLY_FLAG_DONE     = 1 << 0

NBD_EPERM       = 1
NBD_EIO         = 5
NBD_ENOMEM      = 12
NBD_EINVAL      = 22
NBD_ENOSPC      = 28
NBD_EOVERFLOW   = 75
NBD_ENOTSUP     = 95
NBD_ESHUTDOWN   = 108

NBD_RESPONSE_FORMAT = '>4sI8s'
NBD_RESPONSE_MAGIC  = b'\x67\x44\x66\x98'

NBD_FLAG_HAS_FLAGS          = 1 << 0
NBD_FLAG_READ_ONLY          = 1 << 1
NBD_FLAG_SEND_FLUSH         = 1 << 2
NBD_FLAG_SEND_FUA           = 1 << 3
NBD_FLAG_ROTATIONAL         = 1 << 4
NBD_FLAG_SEND_TRIM          = 1 << 5
NBD_FLAG_SEND_WRITE_ZEROES  = 1 << 6
NBD_FLAG_SEND_DF            = 1 << 7
NBD_FLAG_CAN_MULTI_CONN     = 1 << 8
NBD_FLAG_SEND_RESIZE        = 1 << 9
NBD_FLAG_SEND_CACHE         = 1 << 10
NBD_FLAG_SEND_FAST_ZERO     = 1 << 11

NBD_FLAG_FIXED_NEWSTYLE = 1 << 0
NBD_FLAG_NO_ZEROES      = 1 << 1
NBD_FLAG_UNKNOWN_MASK   = (2**16 - 1) ^ (
    NBD_FLAG_FIXED_NEWSTYLE |
    NBD_FLAG_NO_ZEROES
)

NBD_FLAG_C_BYTES_COUNT      = 4
NBD_FLAG_C_FIXED_NEWSTYLE   = 1 << 0
NBD_FLAG_C_NO_ZEROES        = 1 << 1
NBD_FLAG_C_UNKNOWN_MASK     = (2**(NBD_FLAG_C_BYTES_COUNT * 8) - 1) ^ (
    NBD_FLAG_C_FIXED_NEWSTYLE |
    NBD_FLAG_C_NO_ZEROES
)

NBD_INFO_EXPORT         = 0
NBD_INFO_NAME           = 1
NBD_INFO_DESCRIPTION    = 2
NBD_INFO_BLOCK_SIZE     = 3

MAX_OPT_SIZE    = 2**10 # way over any standard OPT request's payload length
MAX_BLOCK_SIZE  = 2**25 # 32M, value recommended in spec

COMMAND_ALLOWED_FLAG_DICT = {
    NBD_CMD_READ:           NBD_CMD_FLAG_FUA | NBD_CMD_FLAG_DF,
    NBD_CMD_WRITE:          NBD_CMD_FLAG_FUA,
    NBD_CMD_DISC:           NBD_CMD_FLAG_FUA,
    NBD_CMD_FLUSH:          NBD_CMD_FLAG_FUA,
    NBD_CMD_TRIM:           NBD_CMD_FLAG_FUA,
    NBD_CMD_CACHE:          NBD_CMD_FLAG_FUA,
    NBD_CMD_WRITE_ZEROES:   NBD_CMD_FLAG_FUA | NBD_CMD_FLAG_NO_HOLE | NBD_CMD_FLAG_FAST_ZERO,
    NBD_CMD_BLOCK_STATUS:   NBD_CMD_FLAG_FUA | NBD_CMD_FLAG_REQ_ONE,
    NBD_CMD_RESIZE:         NBD_CMD_FLAG_FUA,
}

class NBDServer(object):
    """
      Python implementation of NBD protocol.

      Socket handling & event loop must be done outside of this class.
    """

    def __init__(self, sock, device, read_only=False):
        """
          sock (socket)
            Network socket, with an established connection with a client.
          device
            Instance implementing the following methods:
              getSize() -> int
                Size of the underlying storage.
              write(offset, data)
                Write <data> starting at <offset>.
              read(offset, length) -> string
                Read <length> bytes starting at <offset>.
          read_only (bool)
            Whether the device should be advertised as allowing writes.
            This is enforced within this class, so that a client ignoring this
            information will be refused to write anyway.
        """
        self._sock = sock
        self._device = device
        self._read_only = read_only
        self._buffer = buffer = bytearray(MAX_BLOCK_SIZE)
        self._buffer_view = memoryview(buffer)
        self._buffer_len = 0
        self._buffer_target = None

    def fileno(self):
        return self._sock.fileno()

    def close(self):
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
        except OSError as exc:
            if exc.errno != errno.ENOTCONN:
                raise

    def _recvall(self, length):
        result = b''
        while len(result) < length:
            result += self._sock.recv(length - len(result))
        return result

    def _recvOption(self):
        magic, option, length = struct.unpack('>8sII', self._recvall(16))
        assert magic == NBD_CLIENT_OPT_MAGIC, repr(magic)
        if length:
            if length > MAX_OPT_SIZE:
                value = None
            else:
                value = self._recvall(length)
        else:
            value = b''
        return option, value

    def _sendOption(self, option, status, value=b''):
        self._sock.sendall(NBD_SERVER_OPT_MAGIC)
        self._sock.sendall(struct.pack(
            '>III',
            option,
            status,
            len(value),
        ))
        if value:
            self._sock.sendall(value)

    def greet(self):
        """
          To be called upon socket connection establishment.
          Sends NBD server greeting sequence, device size, and whether it is
          read-only.

        """
        self._sock.sendall(NBD_GREETING_PREFIX)
        self._sock.sendall(struct.pack('>H', NBD_FLAG_FIXED_NEWSTYLE | NBD_FLAG_NO_ZEROES))
        handshake_flags, = struct.unpack('>I', self._recvall(NBD_FLAG_C_BYTES_COUNT))
        assert handshake_flags & NBD_FLAG_C_UNKNOWN_MASK == 0, hex(handshake_flags)
        is_no_zeroes = handshake_flags & NBD_FLAG_C_NO_ZEROES
        if handshake_flags & NBD_FLAG_C_FIXED_NEWSTYLE:
            while True:
                option, value = self._recvOption()
                if option == NBD_OPT_EXPORT_NAME:
                    if value is None or value:
                        # NBD_OPT_EXPORT_NAME does not expect a response, so
                        # just close the connection if the name is too long
                        self.close()
                        return False
                    break
                elif value is None: # length exceeded
                    self._sendOption(
                        option=option,
                        status=NBD_REP_ERR_TOO_BIG,
                    )
                elif option == NBD_OPT_ABORT:
                    self._sendOption(
                        option=option,
                        status=NBD_REP_ACK,
                    )
                    self.close()
                    return False
                elif option == NBD_OPT_LIST:
                    if value:
                        self._sendOption(
                            option=option,
                            status=NBD_REP_ERR_INVALID,
                        )
                        continue
                    self._sendOption(
                        option=option,
                        status=NBD_REP_SERVER,
                        value=struct.pack('>I', 0), # empty name
                    )
                    self._sendOption(
                        option=option,
                        status=NBD_REP_ACK,
                    )
                elif option in (NBD_OPT_INFO, NBD_OPT_GO):
                    try:
                        name_length, = struct.unpack('>I', value[:4])
                        name_end = 4 + name_length
                        request_start = name_end + 2
                        name = value[4:name_end]
                        request_count, = struct.unpack(
                            '>H',
                            value[name_end:request_start],
                        )
                    except struct.error:
                        print_exc()
                        print(repr(value))
                        print('name_length:', name_length)
                        print('name_end:', name_end)
                        print('name:', repr(name))
                        print('value[name_end:request_start]:', repr(value[name_end:request_start]))
                        self._sendOption(
                            option=option,
                            status=NBD_REP_ERR_INVALID,
                        )
                        continue
                    if name:
                        print(repr(name))
                        self._sendOption(
                            option=option,
                            status=NBD_REP_ERR_INVALID,
                        )
                        continue
                    transmission_flags = NBD_FLAG_HAS_FLAGS | NBD_FLAG_CAN_MULTI_CONN
                    if self._read_only:
                        transmission_flags |= NBD_FLAG_READ_ONLY
                    self._sendOption(
                        option=option,
                        status=NBD_REP_INFO,
                        value=struct.pack(
                            '>HQH',
                            NBD_INFO_EXPORT,
                            self._device.getSize(),
                            transmission_flags,
                        ),
                    )
                    self._sendOption(
                        option=option,
                        status=NBD_REP_INFO,
                        value=struct.pack(
                            '>H',
                            NBD_INFO_NAME,
                            # empty name
                        ),
                    )
                    self._sendOption(
                        option=option,
                        status=NBD_REP_INFO,
                        value=struct.pack(
                            '>HIII',
                            NBD_INFO_BLOCK_SIZE,
                            1,
                            self._device.getPageSize(),
                            MAX_BLOCK_SIZE,
                        ),
                    )
                    self._sendOption(
                        option=option,
                        status=NBD_REP_ACK,
                    )
                    if option == NBD_OPT_GO:
                        break
                else:
                    self._sendOption(
                        option=option,
                        status=NBD_REP_ERR_UNSUP,
                    )
        else:
            option, value = self._recvOption()
            assert option == NBD_OPT_EXPORT_NAME, hex(option)
            if value:
                self.close()
                return False
        if handshake_flags & NBD_FLAG_C_NO_ZEROES == 0:
            self._sock.sendall(NBD_GREETING_SUFFIX)
        return True

    def _simpleReply(self, handle, error=0, data=b''):
        self._sock.sendall(struct.pack(
            NBD_RESPONSE_FORMAT,
            NBD_RESPONSE_MAGIC,
            error,
            handle,
        ))
        if data:
            self._sock.sendall(data)

    def handle(self):
        """
          To be called upon incomming data on socket.
          Blocks until an entire command has been received, and response had been
          sent back.

          Return values:
            True: operation can continue on socket
            False: error, the socket is now closed
        """
        received = self._buffer_len
        print('reading', NBD_REQUEST_LEN - received)
        received += self._sock.recv_into(
            self._buffer_view[received:],
            NBD_REQUEST_LEN - received,
        )
        print('... got', received)
        if received < NBD_REQUEST_LEN:
            self._buffer_len = received
            return True
        else:
            assert received == NBD_REQUEST_LEN, received
            self._buffer_len = 0
        (magic, flags, command, handle, offset, length) = struct.unpack(
          NBD_REQUEST_FORMAT,
          self._buffer_view[:NBD_REQUEST_LEN],
        )
        if magic != NBD_REQUEST_MAGIC:
            self.close()
            return False
        data = b''
        if flags & ~COMMAND_ALLOWED_FLAG_DICT.get(command, 0):
            error = NBD_ENOTSUP
        elif command == NBD_CMD_READ:
            if flags & NBD_CMD_FLAG_DF:
                error = NBD_ENOTSUP
            elif length > MAX_BLOCK_SIZE:
                error = NBD_EINVAL
            elif length:
                try:
                    data = self._device.read(offset, length)
                except Exception:
                    print_exc()
                    error = NBD_EIO
                else:
                    if len(data) != length:
                        error = NBD_EIO
                        # XXX: no structured reply support
                        data = b''
                    else:
                        error = 0
        elif command == NBD_CMD_WRITE:
            if self._read_only:
                error = NBD_EPERM
            elif length > MAX_BLOCK_SIZE:
                error = NBD_EINVAL
            elif length:
                recv_data = self._recvall(length)
                if len(recv_data) != length:
                    self.close()
                    return False
                try:
                    self._device.write(offset, recv_data)
                except Exception:
                    print_exc()
                    error = NBD_EIO
        elif command == NBD_CMD_DISC:
            self.close()
            return False
        else:
            self._simpleReply(handle, error=NBD_ENOTSUP)
            self.close()
            return False
        self._simpleReply(handle, error=error, data=data)
        return True
