from collections import defaultdict
import logging

"""
Contains functions that read the various files that make up a Wikipedia dump."""

def read_to_set(f):
    """Reads the lines of a file into a set. Used for reading the redirect and
    disambiguation page list files."""
    s = set()
    for l in f:
        l = l.strip()
        s.add(l)
    return s

def read_ids(f):
    """Reads the page id file, and returns two maps: title to id and
    id to title."""
    title_to_id = {}
    id_to_title = {}
    for line in f:
        fields = line.strip().split("\t")
        title_to_id[fields[2]] = int(fields[0])
        id_to_title[int(fields[0])] = fields[2]
    return title_to_id, id_to_title

def read_links(f, title_to_id, id_to_title, reverse=False):
    """Reads the links file and returns it as a map."""
    links = defaultdict(set)
    count = 0
    for line in f:
        count += 1
        if count % 1000000 == 0:
            logging.info("%f read." % (count / 1000000.0))
        fields = line.strip().split("\t")
        src_id = int(fields[0])
        # skip pages that we don't know like useless namespaces
        if not src_id in id_to_title:
            continue

        if fields[1] != "0":
            continue
        try:
            tgt_title = fields[2]
        except IndexError:
            continue
        try:
            tgt_id = title_to_id[tgt_title]
        except KeyError:
            continue
        if not reverse:
            links[tgt_id].add(src_id)
        else:
            links[src_id].add(tgt_id)
    return links

