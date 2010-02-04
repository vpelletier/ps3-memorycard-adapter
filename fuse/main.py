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

def getBlockId(name):
    if name.isdigit():
        result = int(name)
    else:
        result = None
    return result

def asName(block_id):
    return '%02i' % (block_id, )

class PlayStationMemoryCardFS(fuse.Fuse):

    def __getSave(self, name):
        block_id = getBlockId(name)
        if block_id is None:
            result = None
        else:
            result = self.__card_device.getSave(int(name))
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
            block_id = getBlockId(path_element_list[0])
            if block_id is None:
                return -errno.ENOENT
            target_id = self.__card_device.getBlockLinkMap().get(block_id)
            if target_id is None:
                # Unknown: ENOENT
                return -errno.ENOENT
            elif target_id == -1:
                # Orphan block: file
                st.st_mode = stat.S_IFREG
                st.st_nlink = 1
            elif target_id == block_id:
                # Save head: directory
                st.st_mode = stat.S_IFDIR | 0555
                st.st_nlink = 2
            else:
                # Linked block: symlink
                st.st_mode = stat.S_IFLNK | 0777
                st.st_nlink = 1
        elif depth == 0:
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
        else:
            return -errno.ENOENT
        return st

    def readlink(self, path):
        path_element_list = split(path)
        depth = len(path_element_list)
        if depth == 1:
            link_map = self.__card_device.getBlockLinkMap()
            block_id = getBlockId(path_element_list[0])
            if block_id is None:
                return -errno.ENOENT 
            target_id = link_map.get(block_id)
            if target_id is None:
                return -errno.ENOENT
            return asName(target_id)
        else:
            return -errno.ENOENT

    def readdir(self, path, offset):
        for entry in ('.', '..'):
            yield fuse.Direntry(entry)
        path_element_list = split(path)
        depth = len(path_element_list)
        if depth == 0:
            for save_id in self.__card_device.getBlockLinkMap().iterkeys():
                yield fuse.Direntry(asName(save_id))
        elif depth == 1:
            save = self.__getSave(path_element_list[0])
            if save is not None:
                for entry in save.iterEntries():
                    yield fuse.Direntry(entry)
        else:
            yield -errno.ENOENT

    def mkdir(self, path, mode):
        path_element_list = split(path)
        depth = len(path_element_list)
        if depth == 1:
            block_id = getBlockId(path_element_list[0])
            if block_id is None:
                return -errno.EPERM
            try:
                self.__card_device.createSave(block_id)
            except ValueError:
                return -errno.EEXIST
        else:
            return -errno.EPERM

    def rmdir(self, path):
        path_element_list = split(path)
        depth = len(path_element_list)
        if depth == 1:
            block_id = getBlockId(path_element_list[0])
            if block_id is None:
                return -errno.ENOENT
            try:
                self.__card_device.deleteSave(block_id)
            except ValueError:
                return -errno.ENOENT
        else:
            return -errno.ENOENT

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
            return save.read(path_element_list[1], size, offset)
        else:
            return -errno.ENOENT

    def write(self, path, buf, offset):
        path_element_list = split(path)
        if len(path_element_list) == 2:
            save = self.__getSave(path_element_list[0])
            if save is None:
                return -errno.ENOENT
            try:
                result = save.write(path_element_list[1], buf, offset)
            except ValueError:
                result = -errno.EFBIG
            return result
        else:
            return -errno.ENOENT

    def symlink(self, src, dst):
        dst_path_element_list = split(dst)
        if len(dst_path_element_list) == 1:
            src_path_element_list = split(src)
            if len(src_path_element_list) == 1:
                src_block_id = getBlockId(src_path_element_list[0])
                dst_block_id = getBlockId(dst_path_element_list[0])
                if None in (src_block_id, dst_block_id):
                    result = -errno.ENOENT
                else:
                    try:
                        self.__card_device.appendBlock(src_block_id,
                            dst_block_id)
                    except ValueError:
                        result = -errno.EEXIST
                    else:
                        result = 0
            else:
                result = -errno.ENOENT
        else:
            result = -errno.ENOSPC
        return result

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

