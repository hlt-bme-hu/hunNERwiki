import sys
from collections import defaultdict
import logging

"""
This scripts collects all incoming paths that are built of only redirect and
disambiguation pages
Circles are detected and skipped, only a stderr message warns the user.

Formats (description of what a line should contain)(TAB separated inputs):
  page_ids:
    id namespace title is_redirect
  links:
    src_id src_namespace tgt_title
  redirect_pages:
  disambig_pages:
  normal_pages:
    title
"""


def read_to_set(f):
    s = set()
    for l in f:
        l = l.strip()
        s.add(l)
    return s

def read_links(f, title_to_id, id_to_title, reverse=False):
    links = defaultdict(set)
    c = 0
    for l in f:
        c += 1
        if c % 1000000 == 0:
            logging.info("%f read." % (c / 1000000.0))
        le = l.strip().split("\t")
        src_id = int(le[0])
        # skip pages that we don't know like useless namespaces
        if not src_id in id_to_title:
            continue

        if le[1] != "0":
            continue
        try:
            tgt_title = le[2]
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

def read_ids(f):
    title_to_id = {}
    id_to_title = {}
    for l in f:
        le = l.strip().split("\t")
        title_to_id[le[2]] = int(le[0])
        id_to_title[int(le[0])] = le[2]
    return title_to_id, id_to_title

def read_all(redirect_pages_file, disambig_pages_file, normal_pages_file, page_ids_file, links_file, is_reverse):
    redirect_pages = read_to_set(redirect_pages_file)
    disambig_pages = read_to_set(disambig_pages_file)
    normal_pages = read_to_set(normal_pages_file)

    import gc
    gc.disable()
    title_to_id, id_to_title = read_ids(page_ids_file)
    logging.info("ids read.")
    dr_pages = set(title_to_id[page] for page in (redirect_pages | disambig_pages) if page in title_to_id)
    del redirect_pages
    del disambig_pages
    links = read_links(links_file, title_to_id, id_to_title, is_reverse)
    gc.enable()
    return normal_pages, dr_pages, links, (title_to_id, id_to_title)

def run(normal_pages, dr_pages, links, title_to_id, id_to_title, is_reverse):
    logging.info("%d pages to process" % len(normal_pages))
    c = 0
    for page in normal_pages:
        c += 1
        if c % 10000 == 0:
            logging.info("%d pages processed" % c)
        try:
            page_id = title_to_id[page]
        except KeyError:
            logging.info("No id found for page: %s" % page)
            continue
        
        logging.debug("Computing page: %s" % page)
        in_out_pairs = set()
        processed = set()
        to_be_processed = set()
        for neighbour in links[page_id]:
            if neighbour in dr_pages:
                logging.debug("DR page: " + id_to_title[neighbour])
                in_out_pairs.add((neighbour, page_id, "DR"))
                if neighbour not in processed:
                    to_be_processed.add(neighbour)
            else:
                in_out_pairs.add((neighbour, page_id, "Normal"))
        logging.debug("Neighbours added")
        
        while len(to_be_processed) > 0:
            logging.debug("to_be_p length = " + str(len(to_be_processed)))
            actual_processed_node = to_be_processed.pop()
            logging.debug(repr(actual_processed_node))
            
            if actual_processed_node in processed:
                logging.info("There is a circle at \"%s\" started from \"%s\"" % (id_to_title[actual_processed_node], page))
                continue
            
            if len(links[actual_processed_node]) == 0:
                logging.info("RD page (%s) has no target!" % (id_to_title[actual_processed_node]))
            for neighbour in links[actual_processed_node]:
                if neighbour == actual_processed_node:
                    continue
                if neighbour in dr_pages:
                    logging.debug("DR page: " + id_to_title[neighbour])
                    in_out_pairs.add((neighbour, actual_processed_node, "DR"))
                    if neighbour not in processed:
                        to_be_processed.add(neighbour)
                else:
                    in_out_pairs.add((neighbour, actual_processed_node, "Normal"))
            
            processed.add(actual_processed_node)
        
        print "%%#PAGE\t%s" % page
        for pair in in_out_pairs:
            if not is_reverse:
                print "%s\t%s\t%s" % (id_to_title[pair[0]], id_to_title[pair[1]], pair[2])
            else:
                print "%s\t%s\t%s" % (id_to_title[pair[1]], id_to_title[pair[0]], pair[2])

        print

def main():
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s : %(module)s - %(levelname)s - %(message)s")
    page_ids_file = file(sys.argv[1])
    links_file = file(sys.argv[2])
    redirect_pages_file = file(sys.argv[3])
    disambig_pages_file = file(sys.argv[4])
    normal_pages_file = file(sys.argv[5])
    is_reverse = (bool(int(sys.argv[6])) if len(sys.argv) > 6 else False)

    normal_pages, dr_pages, links, (title_to_id, id_to_title) = read_all(redirect_pages_file, disambig_pages_file, normal_pages_file, page_ids_file, links_file, is_reverse)
    #import cProfile
    #cProfile.run("run(normal_pages, dr_pages, links, title_to_id, id_to_title, is_reverse)")
    run(normal_pages, dr_pages, links, title_to_id, id_to_title, is_reverse)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(module)s - %(levelname)s - %(message)s")
    main()

