#!/usr/bin/python
import fuse
import stat    # for file properties
import os      # for filesystem modes (O_RDONLY, etc)
import errno   # for error number codes (ENOENT, etc)
               # - note: these must be returned as negatives
from ps1 import PS1Card

fuse.fuse_python_api = (0, 2)

class PlayStationStat(fuse.Stat):
    st_mode = 0
    st_ino = 0
    st_dev = 0
    st_nlink = 0
    st_uid = 0
    st_gid = 0
    st_size = 0
    st_atime = 0
    st_mtime = 0
    st_ctime = 0

PATH_SEPARATOR = os.path.sep

def split(path):
  return [x for x in path.split(PATH_SEPARATOR) if x]

class PlayStationMemoryCardFS(fuse.Fuse):

    def __getSave(self, name):
        if name.isdigit():
           result = self.__card_device.getSave(int(name))
        else:
           result = None
        return result

    def getattr(self, path):
        st = PlayStationStat()
        path_element_list = split(path)
        depth = len(path_element_list)
        if depth == 2:
            save = self.__getSave(path_element_list[0])
            if save is None:
                return -errno.ENOENT
            st.st_size = save.getEntrySize(path_element_list[1])
            st.st_mode = stat.S_IFREG | 0644
            st.st_nlink = 1
        elif depth == 1:
            st.st_mode = stat.S_IFDIR | 0555
            st.st_nlink = 2
        elif depth == 0:
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
        else:
            return -errno.ENOENT
        return st

    def readdir(self, path, offset):
        for entry in ('.', '..'):
          yield fuse.Direntry(entry)
        path_element_list = split(path)
        depth = len(path_element_list)
        if depth == 0:
            for save_id in self.__card_device.iterSaveIdList():
                yield fuse.Direntry(str(save_id))
        elif depth == 1:
            save = self.__getSave(path_element_list[0])
            if save is not None:
                for entry in save.iterEntries():
                    yield fuse.Direntry(entry)
        else:
            yield -errno.ENOENT

    def open(self, path, flags):
        path_element_list = split(path)
        if len(path_element_list) == 2:
            save = self.__getSave(path_element_list[0])
            if save is None:
                return -errno.ENOENT
            if not save.hasEntry(path_element_list[1]):
                return -errno.ENOENT
        else:
            return -errno.ENOENT

    def read(self, path, size, offset):
        path_element_list = split(path)
        if len(path_element_list) == 2:
            save = self.__getSave(path_element_list[0])
            if save is None:
                return -errno.ENOENT
            return save.getEntry(path_element_list[1])[offset:offset + size]
        else:
            return -errno.ENOENT

    def main(self):
        args = self.cmdline[1]
        assert len(args) == 1, 'Memory card device name expected as argument.'
        if 'ro' in self.fuse_args.optlist:
            mode = ''
        else:
            mode = '+'
        card_device = open(args[0], 'rb' + mode)
        # TODO: detect card type
        self.__card_device = PS1Card(card_device)
        super(PlayStationMemoryCardFS, self).main()

def main():
    server = PlayStationMemoryCardFS(dash_s_do='setsingle')
    server.parse()
    server.main()

if __name__ == '__main__':
    main()

