"""Extracts the page name and type from a dbpedia instance type nt dump.
It is assumed that the types that belong to the same page are in consecutive
lines."""

import re
from langtools.utils.file_utils import FileReader
from langtools.utils.cmd_utils import get_params_sing
from dbpedia_class import OwlClassHierarchy

_type_re = re.compile(r'^\s*<http://dbpedia.org/resource/(.+?)>\s+<http://(.+?)>\s+<http://(.+?)>')
_dbpedia_prefix = 'dbpedia'

def extract_dbpedia_type(type_stream):
    """A generator that reads type_stream line-by-line and outputs page title - 
    NE type pairs.
    @param type_stream: a string iterable in the same format as the dbpedia type
                        file."""
    for line in type_stream:
        match = _type_re.match(line)
        if match:
            if match.group(2).endswith('#type') and match.group(3).startswith(_dbpedia_prefix):
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
    value = set()
    key = ''
    for pair in pairs:
        if key != pair[0]:
            if len(value) > 0:
                yield (key, value)
            key = pair[0]
            value = set()
        value.add(pair[1])
    if len(value) > 0:
        yield (key, list(value))
    return

def filter_general(lines, hierarchy, what_to_keep=None):
    """Filters categories from lines' value list whose descendant categories
    are in the list as well. If the set @p what_to_keep is specified, all
    categories not present in in it are discarded."""
    hierarchy.create_isa_map()
    for line in lines:
        key, values = line
        if what_to_keep is not None:
            values = [v for v in values if v in what_to_keep]
        values.sort(key=hierarchy.get_sorted().get, reverse=True)
        filtered_values = []
        while len(values) > 0:
            curr = values.pop()
            for other in values:
                if hierarchy.is_a(other, curr):
                    break
            else:
                filtered_values.append(curr)
        yield [key, filtered_values]
    return

def filter_type(lines, type_map, keep=False):
    """Filters lines with certain types. Only lines whose types are in the keys
    of C{type_map} are retained and their types are renamed according to the
    mapping in C{type_map}. If @p keep is @c True, the types are not renamed,
    but the new types are appended to the line."""
    for line in lines:
        new_types = []
        for type in line[1]:
            new_type = type_map.get(type)
            if new_type is not None:
                new_types.append(new_type)
        if len(new_types) > 0:
            if keep:
                yield line + [new_types]
            else:
                yield [line[0], new_types]
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
    """Reads the {DBpedia class: ConLL type} mapping."""
    type_map = {}
#    with open(map_file, 'r', encoding = 'utf-8') as mappings:
    with FileReader(map_file, encoding='utf-8').open() as mappings:
        for mapping in mappings:
            try:
                key, value = mapping.strip().split("\t")
                type_map[key] = value
            except (ValueError):
                continue
    return type_map

def print_usage_and_exit():
    sys.stderr.write('Usage: {0} dbpedia_type_file [-c classes_OWL_file] [-m NE_mappings]\n'.format(__file__))
    sys.exit()

if __name__ == '__main__':
    import sys
    try:
        params, args = get_params_sing(sys.argv[1:], 'c:m:k', '', 1)
    except ValueError as ve:
        sys.stderr.write(ve + "\n")
        print_usage_and_exit()
    
    if len(args) != 1:
        print_usage_and_exit()

#    with open(sys.argv[1], 'r', encoding = 'utf-8') as type_stream:
    with FileReader(args[0], encoding='utf-8').open() as type_stream:
        lines = merge_pairs(extract_dbpedia_type(type_stream))
        filter = __read_map(params['m']) if 'm' in params else None
        if 'c' in params:
            lines = filter_general(lines, OwlClassHierarchy(params['c']), filter)
        if 'm' in params:
            lines = filter_type(lines, filter, 'k' in params)
        for line in lines:
            print u"{0}\t{1}".format(line[0], u"\t".join(u' '.join(field) for field in line[1:])).encode('utf-8')

