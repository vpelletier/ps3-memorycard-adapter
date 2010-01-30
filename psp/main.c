#define SERVER_PORT 2000
#define CALLBACKS 1

#include <pspkernel.h>
#include <pspsdk.h>
#include <pspctrl.h>
#include <pspnet.h>
#include <pspnet_inet.h>
#include <pspnet_apctl.h>
#include <psputility_netparam.h>
#include <arpa/inet.h>
#include <pspusb.h>
#include <sys/select.h>

#include <errno.h>
#include <unistd.h>
#include <string.h>

#include "usbsnoopdriver/usbsnoopdriver.h"

#define printf pspDebugScreenPrintf

#define NET_BUF_SIZE 128

PSP_MODULE_INFO("MCAuth", 0, 1, 0);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER);

inline int min(int a, int b) {
  return (a < b) ? a : b;
}

void Error() {
#if CALLBACKS
  sceKernelSleepThread();
#else
  SceCtrlData pad;
  printf("Press X to exit\n");
  while (1)
  {
    sceCtrlReadBufferPositive(&pad, 1);
    if (pad.Buttons & PSP_CTRL_CROSS)
      break;
    sceKernelDelayThread(10000);
  }
  sceKernelExitGame();
#endif
}

#define ENDPOINT_2_FLAG 2
char g_rx_buf[64] __attribute__((aligned(64)));
int g_rx_size;

struct packet_header_t {
  int action;
  int endpoint;
  int length;
} __attribute__((packed));

void hexdump(const char *data, int size) {
  int i;
  for (i=0; i<size; i++) {
    printf(" %02x", data[i] & 0xff);
  }
}

/* Negative lock: 1 means available, 0 means taken */
#define SOCK_WRITE_LOCK_FLAG 1
SceUID sock_write_lock = -1;

int getSockWriteLock(void) {
//  return sceKernelWaitEventFlag(sock_write_lock, SOCK_WRITE_LOCK_FLAG,
//    PSP_EVENT_WAITOR | PSP_EVENT_WAITCLEAR, NULL, NULL);
  return 0;
}

int releaseSockWriteLock(void) {
//  return sceKernelSetEventFlag(sock_write_lock, SOCK_WRITE_LOCK_FLAG);
  return 0;
}

void sockWrite(int client_sock, void *data, int size) {
  if (client_sock) {
    write(client_sock, data, size);
  }
}

void dummy_sockWrite(void *data, int size) {
}

struct usb_data {
  int endpoint;
  int len;
  char data[64];
  int callback_match_len;
  char *(*callback)(char *, int, char *, int);
};

struct command_answer {
  struct usb_data command;
  struct usb_data answer;
};

char *getSeed(char *recv_data, int recv_len, char *seed, int client_sock) {
  return seed;
}

char *toNet(char *recv_data, int recv_len, char *seed, int client_sock) {
  sockWrite(client_sock, recv_data, recv_len);
  return NULL;
}

const struct command_answer KNOWN_COMMANDS[] = {
  {.command = {.endpoint = 2, .len = 2, .data = {0xaa, 0x40}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 2, .data = {0x55, 0x02}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 8, .data = {0xaa, 0x42, 0x04, 0x00, 0x81, 0x11, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 2, .data = {0x55, 0xaf}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf3, 0x00, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},
  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf7, 0x01, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},
  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf0, 0x00, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 0x12, .data = {0xaa, 0x42, 0x0e, 0x00, 0x81, 0xf0, 0x01, 0x00, 0x00,
                                                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 0x12, .data = {0x55, 0x5a, 0x0e, 0x00, 0xff, 0xff, 0xff, 0x2b, 0x45,
                                                    0x42, 0x00, 0x14, 0x00, 0xa2, 0x11, 0x01, 0xa1, 0xff}, .callback = NULL}},
  {.command = {.endpoint = 2, .len = 0x12, .data = {0xaa, 0x42, 0x0e, 0x00, 0x81, 0xF0, 0x02, 0x00, 0x00,
                                                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 0x12, .data = {0x55, 0x5a, 0x0e, 0x00, 0xff, 0xff, 0xff, 0x2b, 0x1d,
                                                    0xc1, 0x8c, 0x00, 0x79, 0x34, 0x00, 0x02, 0x1f, 0xff}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf0, 0x03, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 0x12, .data = {0xAA, 0x42, 0x0e, 0x00, 0x81, 0xF0, 0x04, 0x00, 0x00,
                                                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 0x12, .callback = getSeed}},

  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf0, 0x05, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 0x12, .data = {0xaa, 0x42, 0x0e, 0x00, 0x81, 0xf0, 0x06},
               .callback_match_len=7, .callback=toNet},
   .answer  = {.endpoint = 1, .len = 0x12, .data = {0x55, 0x5a, 0x0e, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff,
                                                    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},
  {.command = {.endpoint = 2, .len = 0x12, .data = {0xaa, 0x42, 0x0e, 0x00, 0x81, 0xf0, 0x07},
               .callback_match_len=7, .callback=toNet},
   .answer  = {.endpoint = 1, .len = 0x12, .data = {0x55, 0x5a, 0x0e, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff,
                                                    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf0, 0x08, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},
  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf0, 0x09, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},
  {.command = {.endpoint = 2, .len = 9, .data = {0xaa, 0x42, 0x05, 0x00, 0x81, 0xf0, 0x0a, 0x00, 0x00}, .callback = NULL},
   .answer  = {.endpoint = 1, .len = 9, .data = {0x55, 0x5a, 0x05, 0x00, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},

  {.command = {.endpoint = 2, .len = 0x12, .data = {0xaa, 0x42, 0x0e, 0x00, 0x81, 0xf0, 0x0b},
               .callback_match_len=7, .callback=toNet},
   .answer  = {.endpoint = 1, .len = 0x12, .data = {0x55, 0x5a, 0x0e, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff,
                                                    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x2b, 0xff}, .callback = NULL}},

};

const struct usb_data *chosen_answer = NULL;
int USBToNet(int endpoint, int *size, void *real_data, int bufsize,
             int client_sock, char *crypto_seed,
             SceUID semaphore, int flag) {
  int res;
  int i;
  char data[64];
  const struct command_answer *current_command_answer;
  const struct usb_data *current_command;

  if (*size < 0) {
    printf("USB %02x Error: %i\n", endpoint, *size);
    return -1;
  }

  memcpy(data, (void *)((int) real_data | 0x40000000), 64);

/*  printf("< %02x %02x ", endpoint, *size);
  hexdump(data, *size);
  printf("\n");*/

  // If the packet matches a known command, answer immediately
  chosen_answer = NULL;
  for (i = 0; i < sizeof(KNOWN_COMMANDS) / sizeof(struct command_answer); i++) {
    current_command_answer = &(KNOWN_COMMANDS[i]);
    current_command = &(current_command_answer->command);
    if (current_command->endpoint == endpoint
        && current_command->len == *size) {
      if (current_command->callback == NULL) {
        if (memcmp(current_command->data, data, current_command->len) == 0) {
          chosen_answer = &(current_command_answer->answer);
        }
      } else {
        if (memcmp(current_command->data, data, current_command->callback_match_len) == 0) {
          current_command->callback(data, *size, NULL, client_sock);
          chosen_answer = &(current_command_answer->answer);
        }
      }
    }
  }

  if (chosen_answer != NULL) {
    char *data;
//    printf("< %02x %02x", chosen_answer->endpoint, chosen_answer->len);
//    hexdump(chosen_answer->data, chosen_answer->len);
//    printf("\n");
    if (chosen_answer->callback == NULL) {
      data = (char *) chosen_answer->data;
    } else {
      data = chosen_answer->callback(NULL, 0, crypto_seed, 0);
/*      printf("> %02x %02x ", chosen_answer->endpoint, chosen_answer->len);
      hexdump(data, chosen_answer->len);
      printf("\n");*/
    }

    res = usbSnoopSendToHost(chosen_answer->endpoint, data,
                             chosen_answer->len);
    if (res) {
      printf("Error sending chosen answer via usb (endp=%02x) %08X\n",
             chosen_answer->endpoint, res);
      return -1;
    }
  } else {
    printf("Unexpected query\n");
    printf("< %02x %02x ", endpoint, *size);
    hexdump(data, *size);
    printf("\n");
    return -1;
  }
  res = usbSnoopRecvFromHost(endpoint, real_data, bufsize, size, semaphore, flag);
  if (res < 0) {
    printf("Failed registering endpoint: 0x%08X\n", res);
    return -1;
  }
  return 0;
}

int sendCryptoResponse(int client_sock, char *crypto_seed) {
  SceUID semaphore;
  int res;
  SceUInt usb_timeout;
  unsigned int semaphore_state;

  semaphore = sceKernelCreateEventFlag("snoopLoop", 0, 0, NULL);
  if (semaphore < 0) {
    printf("Error creating semaphore: 0x%08X\n", semaphore);
    return -1;
  }

  printf("Waiting for device attachment\n");
  res = usbSnoopWaitForAttachment();
  if (res) {
    printf("Error waiting for attachment %08X\n", res);
    return -1;
  }

  res = usbSnoopRecvFromHost(2, g_rx_buf, sizeof(g_rx_buf), &g_rx_size, semaphore, ENDPOINT_2_FLAG);
  if (res < 0) {
    printf("Failed listening on endpoint 2: 0x%08X\n", res);
    return -1;
  }

  printf("Faking PS2 memory card insertion...\n");
  res = usbSnoopSendToHost(3, "\x03", 1);
  if (res) {
    printf("Error in fake card insertion: %08X\n", res);
    return -1;
  }

  while (1) {
    usb_timeout = 100;
    res = sceKernelWaitEventFlag(semaphore, ENDPOINT_2_FLAG,
                                 PSP_EVENT_WAITOR | PSP_EVENT_WAITCLEAR,
                                 &semaphore_state, &usb_timeout);
    if (semaphore_state & ENDPOINT_2_FLAG) {
      if (USBToNet(2, &g_rx_size, g_rx_buf, sizeof(g_rx_buf),
                   client_sock, crypto_seed,
                   semaphore, ENDPOINT_2_FLAG)) {
        break;
      }
    }
  }

  res = usbSnoopCancelRecv(2);
  if (res) {
    printf("Failed to cancel endpoint 2 read: 0x%08X\n", res);
    sceKernelDeleteEventFlag(semaphore);
    return -1;
  }

  sceKernelDeleteEventFlag(semaphore);

  printf("Faking PS2 memory card removal...\n");
  res = usbSnoopSendToHost(3, "\x02", 1);
  if (res) {
    printf("Error in fake card removal: %08X\n", res);
    return -1;
  }

  return 0;
}

#if CALLBACKS
/* Exit callback */
int exit_callback(int arg1, int arg2, void *common)
{
  sceKernelExitGame();
  return 0;
}

/* Callback thread */
int CallbackThread(SceSize args, void *argp)
{
  int cbid;
  cbid = sceKernelCreateCallback("Exit Callback", exit_callback, NULL);
  sceKernelRegisterExitCallback(cbid);
  sceKernelSleepThreadCB();
  return 0;
}

/* Sets up the callback thread and returns its thread id */
int SetupCallbacks(void) {
  int thid = 0;

  thid = sceKernelCreateThread("update_thread", CallbackThread,
                               0x11, 0xFA0, PSP_THREAD_ATTR_USER, 0);
  if(thid >= 0) {
    sceKernelStartThread(thid, 0, 0);
  }

  return thid;
}
#endif

/* Connect to an access point */
int connect_to_apctl(){
  int config = 1;
  int err = 0;
  int stateLast = 0;
  int state = 0;
  int refresh = 1;
  SceCtrlData pad;
  u32 oldButtons = 0;
  netData data;

  while (state == 0 && err == 0) {
    printf("Left/Right: choose. X: connect. O: abort.\n");
    while(1) {
      if (refresh) {
        refresh = 0;
        printf("%d: ", config);
        err = sceUtilityGetNetParam(config, PSP_NETPARAM_NAME, &data);
        if (err) {
          printf("(invalid)");
        } else {
          printf("%s", data.asString);
        }
        // XXX: dirty way of cleaning the rest of the line.
        // Won't work for huge network names.
        printf("                                    \r");
      }
      sceCtrlReadBufferPositive(&pad, 1);
      if (oldButtons != pad.Buttons) {
        if (pad.Buttons & PSP_CTRL_CROSS)
          break;
        else if (pad.Buttons & PSP_CTRL_CIRCLE)
          return 1;
        else if (pad.Buttons & PSP_CTRL_RIGHT) {
          config++;
          refresh = 1;
        } else if (pad.Buttons & PSP_CTRL_LEFT && config > 1) {
          config--;
          refresh = 1;
        }
        oldButtons = pad.Buttons;
      }
      sceKernelDelayThread(10000);
    }

    printf("Connecting... ");
    err = sceNetApctlConnect(config);
    if (err != 0) {
      printf("\nError: sceNetApctlConnect returns %08X\n", err);
      return 0;
    }
    while (1) {
      err = sceNetApctlGetState(&state);
      if (err != 0) {
        printf("\nError: sceNetApctlGetState returns %08X\n", err);
        break;
      }
      if (state != stateLast) {
        // TODO: don't stall when wifi is turned off by switch
        printf("%i \r", state);
        if (state == 0) {
          printf("Failed.\n");
          break;
        } else if (state == 4) {
          printf("Done.\n");
          break;  // connected with static IP
        }
        stateLast = state;
      }
      // wait a little before polling again
      sceKernelDelayThread(50000); // 50ms
    }
  }

  if(err != 0) {
    return 0;
  }

  return 1;
}

int sceKernelSetCompiledSdkVersion(int sdkversion);

int main(int argc, char **argv)
{
  int err;
  struct module_args_t module_args;
  int client_sock = 0;
  int connected = 0;
  pspDebugScreenInit();
  pspDebugScreenClear();

  sceKernelSetCompiledSdkVersion(0x03000310);

#if CALLBACKS
  SetupCallbacks();
#endif

  int modID;
  modID = pspSdkLoadStartModule("flash0:/kd/ifhandle.prx",
                                PSP_MEMORY_PARTITION_KERNEL);
  if (modID < 0) {
    printf("Error loading ifhandle.prx %08X\n", modID);
    Error();
  }
  modID = pspSdkLoadStartModule("flash0:/kd/pspnet.prx",
                                PSP_MEMORY_PARTITION_USER);
  if (modID < 0) {
    printf("Error loading pspnet.prx %08X\n", modID);
    Error();
  }
  modID = pspSdkLoadStartModule("flash0:/kd/pspnet_inet.prx",
                                PSP_MEMORY_PARTITION_USER);
  if (modID < 0) {
    printf("Error loading pspnet_inet.prx %08X\n", modID);
    Error();
  }
  modID = pspSdkLoadStartModule("flash0:/kd/pspnet_apctl.prx",
                                PSP_MEMORY_PARTITION_USER);
  if (modID < 0) {
    printf("Error loading pspnet_apctl.prx %08X\n", modID);
    Error();
  }
  modID = pspSdkLoadStartModule("flash0:/kd/pspnet_resolver.prx",
                                PSP_MEMORY_PARTITION_USER);
  if (modID < 0) {
    printf("Error loading pspnet_resolver.prx %08X\n", modID);
    Error();
  }

  err = pspSdkInetInit();
  if(err) {
    printf("Error, could not initialise the network %08X\n", err);
    Error();
  }

  sock_write_lock = sceKernelCreateEventFlag("SnoopSockWriteLock",
                                             PSP_EVENT_WAITMULTIPLE, 0, NULL);
  if (sock_write_lock < 0) {
    printf("Error creating sock_write_lock: 0x%08X\n", sock_write_lock);
    Error();
  }
  // Lock initially held, so release it.
  releaseSockWriteLock();

  modID = pspSdkLoadStartModule("usbsnoopdriver.prx", PSP_MEMORY_PARTITION_KERNEL);
  if (modID < 0) {
    printf("Error loading usbsnoopdriver.prx %08X\n", modID);
    Error();
  }

  module_args.getSockWriteLock = getSockWriteLock;
  module_args.releaseSockWriteLock = releaseSockWriteLock;
  module_args.sockWrite = dummy_sockWrite;
  err = usbSnoopInit(&module_args);
  if (err) {
    printf("Error, could not initialise usb snoop %08X\n", err);
    Error();
  }

  if(connect_to_apctl())
  {
    int must_exit = 0;
    int sock;
    size_t size;
    struct sockaddr_in name;
    struct sockaddr_in client;
    union SceNetApctlInfo info;

    if ((err = sceNetApctlGetInfo(8, &info))) {
      printf("Error, unknown IP %08X\n", err);
      Error();
    }

    sock = socket(PF_INET, SOCK_STREAM, 0);
    if(sock < 0) {
      printf("Error creating socket %08X\n", sock);
      Error();
    }
    name.sin_family = AF_INET;
    name.sin_port = htons(SERVER_PORT);
    name.sin_addr.s_addr = htonl(INADDR_ANY);
    err = bind(sock, (struct sockaddr *) &name, sizeof(name));
    if(err < 0) {
      printf("Error binding socket %08X\n", err);
      Error();
    }

    err = listen(sock, 1);
    if(err < 0) {
      printf("Error calling listen %08X\n", err);
      Error();
    }

    printf("Listening for connections ip %s port %d\n",
           info.ip, SERVER_PORT);

    while (! must_exit) {
      char crypto_seed[0x12];
      size = sizeof(client);

      if ((!connected) || read(client_sock, crypto_seed, 0x12) != 0x12) {
        if (connected) {
          close(client_sock);
          connected = 0;
        }
        client_sock = accept(sock, (struct sockaddr *) &client, &size);
        if (client_sock < 0) {
          close(sock);
          printf("Error in accept %s\n", strerror(errno));
          must_exit = 1;
        } else {
          connected = 1;
        }
      } else {
        err = sceUsbStart(PSP_USBBUS_DRIVERNAME, 0, NULL);
        if (err) {
          printf("Error starting usb bus driver %08X\n", err);
          Error();
        }

        err = sceUsbStart(SNOOPDRIVER_NAME, 0, NULL);
        if (err) {
          printf("Error starting usb %08X\n", err);
          Error();
        }

        err = sceUsbActivate(SNOOPDRIVER_PID);
        if (err) {
          printf("Error activating usb %08X\n", err);
          Error();
        }

        must_exit = sendCryptoResponse(client_sock, crypto_seed);

        err = sceUsbDeactivate(SNOOPDRIVER_PID);
        if (err) {
          printf("Error deactivating usb %08X\n", err);
          Error();
        }

        err = sceUsbStop(SNOOPDRIVER_NAME, 0, NULL);
        if (err) {
          printf("Error stopping usb %08X\n", err);
          Error();
        }

        err = sceUsbStop(PSP_USBBUS_DRIVERNAME, 0, NULL);
        if (err) {
          printf("Error stopping usb bus driver %08X\n", err);
          Error();
        }
      }
    }
    if (connected) {
      close(client_sock);
    }
  }
  sceKernelExitGame();
  // Never reached
  return 0;
}
