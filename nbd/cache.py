from struct import pack, unpack, calcsize
LEN_FORMAT = '>h'
LEN_LEN = calcsize(LEN_FORMAT)

class FileDictCache(object):
    """
      Simple (de)pickler class for a dictionary of the following structure:
        {string: (string, [...]), [...]}
      values.
      Instances of this class implement basic dict API (__getitem__ and
      __setitem__) and can be used to access file data.

      Important note: the file is only appended to, so updating a dictionary
      entry will actualy append the new value to file.
      Also, there is no support for deleting a dict entry.
    """

    def __init__(self, filename, read_only=True):
        """
          Fetches data from file to populate in-ram dictionary.

          filename (string)
            Name of the file containing pickled data.
          read_only (bool)
            Whether this class should be allowed to write to file.
        """
        self._read_only = read_only
        if read_only:
            mode = 'r'
        else:
            mode = 'a+'
        cache = {}
        self._cache = cache
        cache_file = open(filename, mode + 'b')
        cache_file.seek(0)
        read = cache_file.read
        tell = cache_file.tell

        def readLength():
            len_data = read(LEN_LEN)
            if len(len_data) == LEN_LEN:
                result = unpack(LEN_FORMAT, len_data)[0]
            else:
                result = None
            return result

        def readData():
            length = readLength()
            if length is None:
                result = None
            else:
                result = read(length)
                if len(result) != length:
                    result = None
            return result

        while True:
            record_start = tell()
            key = readData()
            if key is None:
                break
            data_len = readLength()
            if data_len is None:
                raise ValueError('Short read when expecting data length, ' \
                  'record %i corrupted at %i' % (record_start,
                  tell() - record_start))
            data = []
            append = data.append
            for x in range(data_len):
                item = readData()
                if item is None:
                    raise ValueError('Short read when expecting data item, ' \
                      'record %i corrupted at %i' % (record_start,
                      tell() - record_start))
                append(item)
            cache[key] = tuple(data)

        if not read_only:
            self._cache_file = cache_file
            self._cache_to_save = {}

    def __getitem__(self, key):
        return self._cache[key]

    def __setitem__(self, key, value):
        if not isinstance(value, tuple):
            raise TypeError('Value must be a tuple: %r (%s)' % (value,
              type(value)))
        for item in value:
            if not isinstance(item, str):
                raise TypeError('Value elements must be strings: %r (%s) ' \
                  'for value %r' % (item, type(item), value))
        self._cache[key] = value
        if not self._read_only:
            self._cache_to_save[key] = value
            self.flush() # XXX

    def flush(self):
        """
          Store modified entries in file.

          XXX: This is currently always called after a __setitem__. This might
          change, so better to call it explicitely before destructing an instance
          of this class, otherwise you will loose unsaved data.
        """
        if not self._read_only:
            write = self._cache_file.write

            def writeLength(length):
                write(pack(LEN_FORMAT, length))

            def writeData(data):
                writeLength(len(data))
                write(data)

            for key, value in self._cache_to_save.items():
                writeData(key)
                writeLength(len(value))
                for item in value:
                    writeData(item)
            self._cache_file.flush()

            self._cache_to_save = {}

