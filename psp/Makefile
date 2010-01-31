release: all
	make -C usbsnoopdriver
	mksfo 'MCAuth' PARAM.SFO
	pack-pbp EBOOT.PBP PARAM.SFO NULL NULL NULL NULL NULL main.prx NULL

TARGET = main
OBJS = main.o stub.o imports.o

CFLAGS = -O2 -Wall -Werror
CXXFLAGS = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)

BUILD_PRX = 1

LIBS = -lpspusb
LDFLAGS =

PSPSDK=$(shell psp-config --pspsdk-path)

include $(PSPSDK)/lib/build.mak

