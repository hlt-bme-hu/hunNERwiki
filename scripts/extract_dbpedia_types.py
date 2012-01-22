#!/usr/bin/python3
"""Extracts the page name and type from a dbpedia instance type nt dump.
It is assumed that the types that belong to the same page are in consecutive
lines."""

# TODO: rewrite in python2
# TODO: include type hierarchy, prefer more specific types

import re

_type_re = re.compile(r'^\s*<http://dbpedia.org/resource/(.+?)>\s+<http://(.+?)>\s+<http://(.+?)>')

def extract_dbpedia_type(type_stream):
    """A generator that reads type_stream line-by-line and outputs page title - 
    NE type pairs.
    @param type_stream: a string iterable in the same format as the dbpedia type
                        file."""
    for line in type_stream:
        match = _type_re.match(line)
        if match:
            if match.group(2).endswith('#type'):
                title = match.group(1)
                slash = match.group(3).rfind('/')
                if 0 <= slash < len(match.group(3)) - 1:
                    ner_type = match.group(3)[slash + 1:]
                    yield (decode_title(title), ner_type)
    return

def merge_pairs(pairs):
    """Merges subsequent pairs whose key (the first field) is the same. The
    resulting pair will have the same key as the original and a list of the
    values (seconds fields) of the merged pairs as value."""
    value = []
    key = ''
    for pair in pairs:
        if key != pair[0]:
            if len(value) > 0:
                yield (key, value)
            key = pair[0]
            value = []
        value.append(pair[1])
    if len(value) > 0:
        yield (key, value)
    return

def filter_type(pairs, type_map):
    """Filters pairs with certain types. Only pairs whose keys are in the keys
    of C{type_map} are retained and their keys are renamed according to the
    mapping in C{type_map}."""
    for pair in pairs:
        new_type = type_map.get(pair[1])
        if new_type:
            yield (pair[0], new_type)
    return

def decode_title(title):
    """This method does two things. First, it replaces underscores by spaces
    in the page title; second, it decodes the encoded unicode characters.
    The characters are encoded bytewise as a hexadecimal number preceded by a
    percent sign (e.g. C{%C3%A8}). Also, underscores are replaced by spaces"""
    mode = 0
    ret = bytearray()
    for c in title:
        if mode == 0:
            if c == '%':
                mode = 2
            else:
                if c == '_':
                    ret.append(ord(' '))
                else:
                    ret.append(ord(c))
        elif mode == 2:
            prev_c = c
            mode -= 1
        else:
            ret.append(int(prev_c + c, 16))
            mode = 0
    return ret.decode('utf-8')

def __read_map(map_file):
    type_map = {}
    with open(map_file, 'r', encoding = 'utf-8') as mappings:
        for mapping in mappings:
            try:
                key, value = mapping.strip().split(' ')
                type_map[key] = value
            except (ValueError):
                continue
    return type_map

if __name__ == '__main__':
    import sys
    if not 2 <= len(sys.argv) <= 3:
        sys.stderr.write('Usage: {0} dbpedia_type_file [NE_mappings]\n'.format(
            __file__))
        sys.exit()
    with open(sys.argv[1], 'r', encoding = 'utf-8') as type_stream:
        pairs = extract_dbpedia_type(type_stream)
        if len(sys.argv) == 3:
            pairs = filter_type(pairs, __read_map(sys.argv[2]))
        for pair in merge_pairs(pairs):
            print('{0}\t{1}'.format(pair[0], ' '.join(pair[1])))

