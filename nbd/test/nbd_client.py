import struct
import socket

def hexdump(data):
  return ' '.join('%02x' % (ord(x), ) for x in data)

sock = socket.socket()
sock.connect(('127.0.0.1', 20530))
print hexdump(sock.recv(16+128+8))
sock.send('\x25\x60\x95\x13' + struct.pack('>L8sQL', 0, '00000000', 0x1000, 0x1000))
print hexdump(sock.recv(16))

