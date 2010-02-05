import socket
import time
SEED_LENGTH = 9

class SockAuthenticator(object):
    """
      Class to fetch authentication data through a connection to an
      authentication server.
    """
    def __init__(self, ip, port, authentication_cache=None):
        """
          ip (string)
            Address of the authentication server.
          port (int)
            Port of the authentication server.
          authentication_cache (dict-ish, or None)
            Used to store and retrieve cached authentication data.
            If None (default), a volatile cache will be used (it will be destroyed
            when the instance is destroyed).
        """
        self._ip = ip
        self._port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._connected = False
        if authentication_cache is None:
            authentication_cache = {}
        self._authentication_cache = authentication_cache

    def authenticate(self, seed):
        """
          Send seed to authentication server.
          seed (string)
            This value must have a length of 9

          Return value: 3-tuple of strings.
        """
        try:
            result = self._authentication_cache[seed]
        except KeyError:
            if len(seed) != SEED_LENGTH:
                raise ValueError, 'Invalid seed length: %i, expected %i' % (
                    len(seed), SEED_LENGTH)
            sock = self._socket
            if not self._connected:
                self._connected = True
                sock.connect((self._ip, self._port))
            sock.send('\x55\x5a\x0e\x00\xff\xff\xff\x2b' + seed + '\xff')
            result = tuple([sock.recv(0x12)[7:-2] for x in xrange(3)])
            self._authentication_cache[seed] = result
        return result

class CachedAuthenticator(object):
    def __init__(self, authentication_cache):
        self._authentication_cache = authentication_cache

    def authenticate(self, seed):
        try:
            result = self._authentication_cache[seed]
        except KeyError:
            # Sleep so auth timeouts
            time.sleep(1)
            # In case it doesn't, provide a dummy default
            result = ['\x00' * 9] * 3
        return result

