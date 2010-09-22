#include <pspkernel.h>
#include <pspdebug.h>
#include <pspkdebug.h>
#include <pspsdk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pspusb.h>
#include <pspusbbus.h>
#include "usbsnoopdriver.h"

#define ENDPOINT_COUNT 4
#define ENDPOINT_DESCRIPTOR_COUNT (ENDPOINT_COUNT - 1)

/* XXX: the exact set of required flags is unknown. */
PSP_MODULE_INFO(MODULE_NAME, PSP_MODULE_KERNEL | PSP_MODULE_SINGLE_START |
        PSP_MODULE_SINGLE_LOAD | PSP_MODULE_NO_STOP, 1, 1);

enum UsbEvents {
  SEND_TO_HOST_FLAG = 1,
  HOST_ATTACHED_FLAG = 2,
};

struct UsbDeviceReqParam {
  SceUID user_event;
  int user_event_flag;
  int *recv_size;
};

static SceUID g_events = -1;

/* HI-Speed device descriptor */
struct DeviceDescriptor devdesc_hi = {
	.bLength = 18,
	.bDescriptorType = 0x01,
	.bcdUSB = 0x200,
	.bDeviceClass = 0xff, //0,
	.bDeviceSubClass = 0,
	.bDeviceProtocol = 0xff, //0,
	.bMaxPacketSize = 64,
	.idVendor = SONY_VID, //0,
	.idProduct = SNOOPDRIVER_PID, //0,
	.bcdDevice = 0x100,
	.iManufacturer = 0,
	.iProduct = 0,
	.iSerialNumber = 0,
	.bNumConfigurations = 1
};

/* Hi-Speed configuration descriptor */
struct ConfigDescriptor confdesc_hi = {
	.bLength = 9,
	.bDescriptorType = 2,
	.wTotalLength = (9+9+(3*7)),
	.bNumInterfaces = 1,
	.bConfigurationValue = 1,
	.iConfiguration = 0,
	.bmAttributes = 0x80, //0xC0,
	.bMaxPower = 100 //0
};

/* Hi-Speed interface descriptor */
struct InterfaceDescriptor interdesc_hi = {
	.bLength = 9,
	.bDescriptorType = 4,
	.bInterfaceNumber = 0,
	.bAlternateSetting = 0,
	.bNumEndpoints = 3,
	.bInterfaceClass = 0xFF,
	.bInterfaceSubClass = 0, //0x1,
	.bInterfaceProtocol = 0xFF,
	.iInterface = 0 //1
};

/* Hi-Speed endpoint descriptors */
struct EndpointDescriptor endpdesc_hi[ENDPOINT_DESCRIPTOR_COUNT] = {{
		.bLength = 7,
		.bDescriptorType = 5,
		.bEndpointAddress = 0x81,
		.bmAttributes = 2,
		.wMaxPacketSize = 64, //512,
		.bInterval = 0
	}, {
		.bLength = 7,
		.bDescriptorType = 5,
		.bEndpointAddress = 2,
		.bmAttributes = 2,
		.wMaxPacketSize = 64, //512,
		.bInterval = 0
	}, {
		.bLength = 7,
		.bDescriptorType = 5,
		.bEndpointAddress = 0x83, //3,
		.bmAttributes = 3, //2,
		.wMaxPacketSize = 1, //512,
		.bInterval = 100 //0
}};

/* Full-Speed device descriptor */
struct DeviceDescriptor devdesc_full = {
	.bLength = 18,
	.bDescriptorType = 0x01,
	.bcdUSB = 0x101, //0x200,
	.bDeviceClass = 0xff, //0,
	.bDeviceSubClass = 0,
	.bDeviceProtocol = 0xff, //0,
	.bMaxPacketSize = 64,
	.idVendor = SONY_VID, //0,
	.idProduct = SNOOPDRIVER_PID, //0,
	.bcdDevice = 0x100,
	.iManufacturer = 0,
	.iProduct = 0,
	.iSerialNumber = 0,
	.bNumConfigurations = 1
};

/* Full-Speed configuration descriptor */
struct ConfigDescriptor confdesc_full = {
	.bLength = 9,
	.bDescriptorType = 2,
	.wTotalLength = (9+9+(3*7)),
	.bNumInterfaces = 1,
	.bConfigurationValue = 1,
	.iConfiguration = 0,
	.bmAttributes = 0x80, //0xC0,
	.bMaxPower = 100 //0
};

/* Full-Speed interface descriptor */
struct InterfaceDescriptor interdesc_full = {
	.bLength = 9,
	.bDescriptorType = 4,
	.bInterfaceNumber = 0,
	.bAlternateSetting = 0,
	.bNumEndpoints = 3,
	.bInterfaceClass = 0xFF,
	.bInterfaceSubClass = 0, //0x1,
	.bInterfaceProtocol = 0xFF,
	.iInterface = 0 //1
};

/* Full-Speed endpoint descriptors */
struct EndpointDescriptor endpdesc_full[ENDPOINT_DESCRIPTOR_COUNT] = {{
		.bLength = 7,
		.bDescriptorType = 5,
		.bEndpointAddress = 0x81,
		.bmAttributes = 2,
		.wMaxPacketSize = 64,
		.bInterval = 0
	}, {
		.bLength = 7,
		.bDescriptorType = 5,
		.bEndpointAddress = 2,
		.bmAttributes = 2,
		.wMaxPacketSize = 64,
		.bInterval = 0
	}, {
		.bLength = 7,
		.bDescriptorType = 5,
		.bEndpointAddress = 0x83, //3,
		.bmAttributes = 3, //2,
		.wMaxPacketSize = 1, //64,
		.bInterval = 100 //0
}};

/* String descriptor */
unsigned char strp[] = {
	0x8, 0x3, '<', 0, '>', 0, 0, 0
};

/* Endpoint blocks */
struct UsbEndpoint endp[ENDPOINT_COUNT] = {
	{ 0, 0, 0 },
	{ 1, 0, 0 },
	{ 2, 0, 0 },
	{ 3, 0, 0 },
};

/* Intefaces */
struct UsbInterface intp = {
	0xFFFFFFFF, 0, 1,
};

int (*getSockWriteLock)(void);
int (*releaseSockWriteLock)(void);
void (*sockWrite)(void *data, int size);

struct packet_header_t {
  int action;
  int req_len;
  int data_len;
} __attribute__((packed));

/* Device request */
int usb_request(int arg1, int arg2, struct DeviceRequest *req) {
  void *data = (void *) arg2;
  if (getSockWriteLock && releaseSockWriteLock && sockWrite) {
    int k1;
    k1 = pspSdkSetK1(0);
    struct packet_header_t packet_header;
    packet_header.action = USB_EXCHANGE_TYPE_REQUEST;
    packet_header.req_len = sizeof(struct DeviceRequest);
    packet_header.data_len = req->wLength;
    if (getSockWriteLock() == 0) {
      sockWrite(&packet_header, sizeof(struct packet_header_t));
      sockWrite(req, sizeof(struct DeviceRequest));
      sockWrite(data, req->wLength);
      releaseSockWriteLock();
    }
    pspSdkSetK1(k1);
  }
  return 0;
}

/* Unknown callback */
int func28(int arg1, int arg2, int arg3) {
	return 0;
}

/* Attach callback, speed 1=full, 2=hi  */
int usb_attach(int speed, void *arg2, void *arg3) {
	sceKernelSetEventFlag(g_events, HOST_ATTACHED_FLAG);
	return 0;
}

/* Detach callback */
int usb_detach(int arg1, int arg2, int arg3) {
	sceKernelClearEventFlag(g_events, HOST_ATTACHED_FLAG);
	return 0;
}

/* Forward define the driver structure */
extern struct UsbDriver g_driver;

/* USB data structures for hi and full speed endpoints */
struct UsbData usbdata[2];

int usbSnoopIsAttached(u32 *flags) {
  return sceKernelPollEventFlag(g_events, HOST_ATTACHED_FLAG, PSP_EVENT_WAITOR, flags);
}

int usbSnoopWaitForAttachment(void) {
  int k1;
  k1 = pspSdkSetK1(0);
  return sceKernelWaitEventFlag(g_events, HOST_ATTACHED_FLAG, PSP_EVENT_WAITOR, NULL, NULL);
  pspSdkSetK1(k1);
}

/* Callback for when a usbSnoopSendToHost request is done */
int send_to_host_req_done(struct UsbdDeviceReq *req, int arg2, int arg3) {
  sceKernelSetEventFlag(g_events, SEND_TO_HOST_FLAG);
  return 0;
}

/* Data send (sync) */
int usbSnoopSendToHost(int endp_index, void *data, int size) {
  int res;
  u32 result;
  struct UsbdDeviceReq send_req;
  int k1;
  k1 = pspSdkSetK1(0);

  sceKernelDcacheWritebackRange(data, size);
  memset(&send_req, 0, sizeof(struct UsbdDeviceReq));
  send_req.endp = &endp[endp_index];
  send_req.data = data;
  send_req.size = size;
  send_req.func = send_to_host_req_done;
  sceKernelClearEventFlag(g_events, ~SEND_TO_HOST_FLAG);
  res = sceUsbbdReqSend(&send_req);
  if (res) {
    pspSdkSetK1(k1);
    return res;
  }
  res = sceKernelWaitEventFlag(g_events, SEND_TO_HOST_FLAG,
                               PSP_EVENT_WAITOR | PSP_EVENT_WAITCLEAR,
                               &result, NULL);
  pspSdkSetK1(k1);
  return res;
}

/* Callback for when a usbSnoopRecvFromHost request is done */
int recv_from_host_req_done(struct UsbdDeviceReq *req, int arg2, int arg3) {
  struct UsbDeviceReqParam *recv_param = (struct UsbDeviceReqParam *) req->arg;
  if (req->retcode < 0) {
    *(recv_param->recv_size) = req->retcode;
  } else {
    *(recv_param->recv_size) = req->recvsize;
  }
  sceKernelDcacheInvalidateRange(req->data, req->size + (0x3f - (req->size & 0x3f)));
  sceKernelSetEventFlag(recv_param->user_event, recv_param->user_event_flag);
  return 0;
}

static struct UsbdDeviceReq g_recv_req[ENDPOINT_COUNT];
static struct UsbDeviceReqParam g_recv_param[ENDPOINT_COUNT];

/* Data recv (async) */
int usbSnoopRecvFromHost(int endp_index, void *data, int size,
                         int *recv_size, SceUID user_event, int user_event_flag) {
  struct UsbdDeviceReq *recv_req;
  struct UsbDeviceReqParam *recv_param;
  int res = 0;
  int k1;

  if ((int) data & 0x3f) {
    return -1;
  }

  if (endp_index > ENDPOINT_COUNT) {
    return -2;
  }

  k1 = pspSdkSetK1(0);

  /* Invalidate range */
  //sceKernelDcacheInvalidateRange(data, size + (0x3f - (size & 0x3f)));

  recv_req = &g_recv_req[endp_index];
  recv_param = &g_recv_param[endp_index];
  recv_param->user_event = user_event;
  recv_param->user_event_flag = user_event_flag;
  recv_param->recv_size = recv_size;

  memset(recv_req, 0, sizeof(struct UsbdDeviceReq));
  recv_req->data = data;
  recv_req->size = size;
  recv_req->endp = &endp[endp_index];
  recv_req->func = recv_from_host_req_done;
  recv_req->arg = (void *) recv_param;
  res = sceKernelClearEventFlag(user_event, ~user_event_flag);
  if (res < 0) {
    pspSdkSetK1(k1);
    return res;
  }
  res = sceUsbbdReqRecv(recv_req);
  pspSdkSetK1(k1);
  return res;
}

int usbSnoopCancelRecv(int endp_index) {
  int k1;
  int res;
  k1 = pspSdkSetK1(0);
  if (endp_index > ENDPOINT_COUNT) {
    pspSdkSetK1(k1);
    return -2;
  }
  res = sceUsbbdReqCancelAll(&endp[endp_index]);
  pspSdkSetK1(k1);
  return res;
}

int usbSnoopInit(struct module_args_t *arg){
  int k1;
  k1 = pspSdkSetK1(0);
  getSockWriteLock = arg->getSockWriteLock;
  releaseSockWriteLock = arg->releaseSockWriteLock;
  sockWrite = arg->sockWrite;
  pspSdkSetK1(k1);
  return 0;
}

/* USB start function */
int start_func(int size, void *p)
{
	/* Fill in the descriptor tables */
	memset(usbdata, 0, sizeof(usbdata));

	memcpy(usbdata[0].devdesc, &devdesc_hi, sizeof(devdesc_hi));
	usbdata[0].config.pconfdesc = &usbdata[0].confdesc;
	usbdata[0].config.pinterfaces = &usbdata[0].interfaces;
	usbdata[0].config.pinterdesc = &usbdata[0].interdesc;
	usbdata[0].config.pendp = usbdata[0].endp;
	memcpy(usbdata[0].confdesc.desc, &confdesc_hi,  sizeof(confdesc_hi));
	usbdata[0].confdesc.pinterfaces = &usbdata[0].interfaces;
	usbdata[0].interfaces.pinterdesc[0] = &usbdata[0].interdesc;
	usbdata[0].interfaces.intcount = 1;
	memcpy(usbdata[0].interdesc.desc, &interdesc_hi, sizeof(interdesc_hi));
	usbdata[0].interdesc.pendp = usbdata[0].endp;
	memcpy(usbdata[0].endp[0].desc, &endpdesc_hi[0], sizeof(endpdesc_hi[0]));
	memcpy(usbdata[0].endp[1].desc, &endpdesc_hi[1], sizeof(endpdesc_hi[1]));
	memcpy(usbdata[0].endp[2].desc, &endpdesc_hi[2], sizeof(endpdesc_hi[2]));

	memcpy(usbdata[1].devdesc, &devdesc_full, sizeof(devdesc_full));
	usbdata[1].config.pconfdesc = &usbdata[1].confdesc;
	usbdata[1].config.pinterfaces = &usbdata[1].interfaces;
	usbdata[1].config.pinterdesc = &usbdata[1].interdesc;
	usbdata[1].config.pendp = usbdata[1].endp;
	memcpy(usbdata[1].confdesc.desc, &confdesc_full,  sizeof(confdesc_full));
	usbdata[1].confdesc.pinterfaces = &usbdata[1].interfaces;
	usbdata[1].interfaces.pinterdesc[0] = &usbdata[1].interdesc;
	usbdata[1].interfaces.intcount = 1;
	memcpy(usbdata[1].interdesc.desc, &interdesc_full, sizeof(interdesc_full));
	usbdata[1].interdesc.pendp = usbdata[1].endp;
	memcpy(usbdata[1].endp[0].desc, &endpdesc_full[0], sizeof(endpdesc_full[0]));
	memcpy(usbdata[1].endp[1].desc, &endpdesc_full[1], sizeof(endpdesc_full[1]));
	memcpy(usbdata[1].endp[2].desc, &endpdesc_full[2], sizeof(endpdesc_full[2]));

	g_driver.devp_hi = usbdata[0].devdesc;
	g_driver.confp_hi = &usbdata[0].config;
	g_driver.devp = usbdata[1].devdesc;
	g_driver.confp = &usbdata[1].config;

        g_events = sceKernelCreateEventFlag("USBSnoopEvent", 0x200, 0, NULL);
        if(g_events < 0) {
                return -1;
        }

	return 0;
}

/* USB stop function */
int stop_func(int size, void *p) {
        if(g_events >= 0) {
                sceKernelDeleteEventFlag(g_events);
                g_events = -1;
        }

	return 0;
}

/* USB host driver */
struct UsbDriver g_driver = {
	.name = SNOOPDRIVER_NAME,
	.endpoints = ENDPOINT_COUNT,
	.endp = endp,
	.intp = &intp,
	.devp_hi = NULL, .confp_hi = NULL, .devp = NULL, .confp = NULL,
	.str = (struct StringDescriptor *) strp,
	.recvctl = usb_request, .func28 = func28, .attach = usb_attach, .detach = usb_detach,
	.unk34 = 0,
	.start_func = start_func,
	.stop_func = stop_func,
	.link = NULL
};

/* Entry point */

int module_start(SceSize args, void *argp) {
  return sceUsbbdRegister(&g_driver);
}

/* Module stop entry */
int module_stop(SceSize args, void *argp) {
  return sceUsbbdUnregister(&g_driver);
}
