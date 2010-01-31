#!/usr/bin/python
def main(options):
  import socket
  import usb1
  from nbd import NBDServer
  from cache import FileDictCache
  from authenticator import SockAuthenticator
  from memory_card_reader import PlayStationMemoryCardReader
  nbd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  nbd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  nbd_sock.bind((options.nbd_address, options.nbd_port))
  nbd_sock.listen(1)
  authentication_cache = FileDictCache(options.auth_cache,
    read_only=options.auth_cache_read_only)
  authenticator = SockAuthenticator(options.auth_address, options.auth_port,
    authentication_cache)
  try:
    usb_context = usb1.LibUSBContext()
    usb_device = usb_context.openByVendorIDAndProductID(0x054c, 0x02ea)
    usb_device.claimInterface(0)
    reader = PlayStationMemoryCardReader(usb_device, authenticator)
    print 'Waiting for client...'
    while True:
      (nbd_client_sock, addr) = nbd_sock.accept()
      print 'Client connected %s:%i' % addr
      nbd_server = NBDServer(reader)
      nbd_server.greet(nbd_client_sock)
      while nbd_server.handle(nbd_client_sock):
        pass
      nbd_client_sock.shutdown(socket.SHUT_RDWR)
      nbd_client_sock.close()
      print 'Client disconnected'
  finally:
    usb_device.releaseInterface(0)
    usb_device.close()
    usb_context.exit()
    nbd_sock.shutdown(socket.SHUT_RDWR)
    nbd_sock.close()

if __name__ == '__main__':
  from optparse import OptionParser

  parser = OptionParser()
  parser.add_option('-p', '--nbd-port', default=20530, type='int',
    help='Port the embeded NBD server will listen on.')
  parser.add_option('-a', '--nbd-address', default='',
    help='Address the embeded NBD server will listen on.')
  parser.add_option('-c', '--auth-cache', default='auth_cache.bin',
    help='File containing authentication data from previous sessions.')
  parser.add_option('-r', '--auth-cache-read-only', default=False,
    action='store_true',
    help='Don\'t store authentication information generated during this run.')
  parser.add_option('-P', '--auth-port', default=20531, type='int',
    help='Port used to contact authentication daemon.')
  parser.add_option('-A', '--auth-address', default='127.0.0.1',
    help='Address used to contact authentication daemon.')
  (options, args) = parser.parse_args()
  main(options)

