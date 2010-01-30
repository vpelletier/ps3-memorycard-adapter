.set noreorder

#include "pspstub.s"

	STUB_START "SysMemUserForUser",0x40090000,0x00010005
	STUB_FUNC  0x7591C7DB,sceKernelSetCompiledSdkVersion
	STUB_END