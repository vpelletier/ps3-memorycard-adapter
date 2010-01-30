#ifndef __USBSNOOPRELAY_H__
#define __USBSNOOPRELAY_H__

#include <stdint.h>

#define MODULE_NAME "USBSnoopRelay"
#define SNOOPDRIVER_NAME "USBSnoopRelayDriver"
#define SNOOPDRIVER_PID  (0x2ea)
#define SONY_VID (0x54C)

#define USB_EXCHANGE_TYPE_DATA 1
#define USB_EXCHANGE_TYPE_PING 2
#define USB_EXCHANGE_TYPE_REQUEST 3

#ifdef DEBUG
#define DEBUG_PRINTF(fmt, ...) Kprintf("%s: " fmt, MODULE_NAME, ## __VA_ARGS__)
#else
#define DEBUG_PRINTF(fmt, ...)
#endif

#define MODPRINTF DEBUG_PRINTF

int usbSnoopSendToHost(int endp_index, void *data, int size);
int usbSnoopRecvFromHost(int endp_index, void *data, int size, int *recv_size,
                         SceUID user_event, int user_event_flag);
int usbSnoopCancelRecv(int endp_index);
int usbSnoopIsAttached(u32 *flags);
int usbSnoopWaitForAttachment(void);

struct module_args_t {
  int (*getSockWriteLock)(void);
  int (*releaseSockWriteLock)(void);
  void (*sockWrite)(void *data, int size);
};

int usbSnoopInit(struct module_args_t *);

#endif /* __USBSNOOPRELAY_H__ */
