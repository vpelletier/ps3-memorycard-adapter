#!/usr/bin/python
def main():
  import socket
  import usb1
  from nbd import NBDServer
  from cache import FileDictCache
  from authenticator import SockAuthenticator
  from memory_card_reader import PlayStationMemoryCardReader
  # TODO: parse args and replace this hardcoded class
  class options:
    nbd_ip = ''
    nbd_port = 20530
    auth_cache_file = 'auth_cache.bin'
    auth_cache_read_only = False
    auth_ip = '192.168.0.20'
    auth_port = 2000
  nbd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  #nbd_sock_fd = nbd_sock.fileno()
  nbd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  nbd_sock.bind((options.nbd_ip, options.nbd_port))
  nbd_sock.listen(1)
  authentication_cache = FileDictCache(options.auth_cache_file,
    read_only=options.auth_cache_read_only)
  authenticator = SockAuthenticator(options.auth_ip, options.auth_port,
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
    usb_device.close()
    usb_context.exit()
    nbd_sock.shutdown(socket.SHUT_RDWR)
    nbd_sock.close()

if __name__ == '__main__':
  main()

