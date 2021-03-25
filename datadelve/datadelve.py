import collections
import json
from pathlib import Path
from typing import Dict, Any, Union, List

import jsonpointer


class DelverError(Exception):
    pass


class ReadonlyError(DelverError):
    pass


class PathError(DelverError, ValueError):
    pass


class MissingFileError(DelverError):
    pass


class MergeError(DelverError, TypeError):
    pass


class DataDelver:
    class JsonPointerCache:
        def __init__(self):
            self.cache = {}

        def __getitem__(self, key: str) -> jsonpointer.JsonPointer:
            if key not in self.cache:
                self.cache[key] = jsonpointer.JsonPointer(key)
            return self.cache[key]

    def __init__(self, data: Union[list, Dict[str, Any]], readonly=False, basepath=""):
        self.data = data
        self.basepath = basepath.rstrip('/')
        self.readonly = readonly
        self._cache = type(self).JsonPointerCache()

    def __iter__(self):
        obj = self.get('')
        if isinstance(obj, dict):
            yield from obj.items()
        elif isinstance(obj, list):
            yield from obj

    def get(self, path: str):
        if self.basepath + path == '':
            return self.data
        pointer = self._cache[self.basepath + path]
        return pointer.resolve(self.data, None)

    def delete(self, path):
        if self.readonly:
            raise ReadonlyError('{} is readonly'.format(self.data))
        if self.basepath + path == '':
            self.data = {}
            return
        pointer = self._cache[self.basepath + path]
        subdoc, key = pointer.to_last(self.data)
        del subdoc[key]

    def set(self, path, value):
        if self.readonly:
            raise ReadonlyError('{} is readonly'.format(self.data))
        if self.basepath + path == '':
            self.data = value
            return
        pointer = self._cache[self.basepath + path]
        pointer.set(self.data, value)

    def cd(self, path, readonly=False):
        return DataDelver(self.data, readonly=self.readonly or readonly,
                          basepath=self.basepath + path)


class JsonDelver(DataDelver):
    __EXTANT = {}

    def __new__(cls, path: Union[Path, str], **kwargs):
        if str(path) in cls.__EXTANT:
            return cls.__EXTANT[str(path)]
        else:
            obj = super().__new__(cls)
            return obj

    def __init__(self, filename: Union[Path, str], readonly=False):
        self.filename = Path(filename)
        with self.filename.open('r') as f:
            data = json.load(f, object_pairs_hook=collections.OrderedDict)
            super().__init__(data, readonly)
        type(self).__EXTANT[str(self.filename)] = self

    def __repr__(self):
        return "<JsonDelver to {}>".format(self.filename)

    def __str__(self):
        return self.filename.name

    def write(self):
        if self.readonly:
            raise ReadonlyError("Trying to write a readonly file")
        with open(self.filename, 'w') as f:
            json.dump(self.data, f, indent=2)


class ChainedDelver:
    def __init__(self, *interfaces: JsonDelver):
        """Delvers should come in order from least to most specific"""
        self.searchpath = collections.OrderedDict(
            (str(inter.filename), inter) for inter in interfaces)

    def __getitem__(self, item: str) -> JsonDelver:
        return self.searchpath[item]

    def _most_to_least(self):
        return reversed(self.searchpath.values())

    def _least_to_most(self):
        return self.searchpath.values()

    def _first(self, path: str):
        for delver in self._most_to_least():
            found = delver.get(path)
            if found is not None:
                return found
        return None

    def _merge(self, path: str) -> Union[list, dict]:
        collected = None
        merger = None
        for delver in self._least_to_most():
            found = delver.get(path)
            if found is not None:
                if collected is None:
                    collected = found
                    if isinstance(found, dict):
                        merger = dict.update
                    elif isinstance(found, list):
                        merger = list.extend
                    else:
                        raise MergeError("Can only merge collections, not {!r}".format(found))
                else:
                    merger(collected, found)
        return collected

    def _collect(self, path: str) -> List[Any]:
        every = []
        for delver in self._most_to_least():
            found = delver.get(path)
            if found is not None:
                every.append(found)
        return every

    def get(self, path: str, strategy: str = 'first'):
        strategies = {
            'first': self._first,
            'merge': self._merge,
            'collect': self._collect,
        }
        return strategies[strategy](path)
