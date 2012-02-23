import sys
import logging
from read_wiki_files import read_ids, read_to_set, read_links
from optparse import OptionParser

"""Resolves redirect pages and tags them with the same NER categories as the
target pages."""

def read_all(redirect_pages_file, page_ids_file, links_file):
    """Reads the files necessary for the resolution of redirects.
    Returns: - the ids of the redirect pages;
             - the links map, reversed;
             - the title to id map;
             - the id to title map."""
    redirect_pages = read_to_set(redirect_pages_file)
    logging.info("Redirect pages read.")

    import gc
    gc.disable()
    title_to_id, id_to_title = read_ids(page_ids_file)
    logging.info("Ids read.")
    redirect_ids = set(title_to_id.get(page) for page in redirect_pages)
    redirect_ids -= set([None])
    del redirect_pages
    links = read_links(links_file, title_to_id, id_to_title, True)
    gc.enable()
    return redirect_ids, links, title_to_id, id_to_title

def run(map_file, redirect_ids, links, title_to_id, id_to_title):
    for line in map_file:
        try:
            page_title, ner = line.strip().split("\t")
        except IndexError:
            continue

        try:
            page_id = title_to_id[page_title]
        except KeyError:
            logging.warning("No id found for page: " + page_title)
            continue

        redirect_ids = links.get(page_id, [])
        for redirect_id in redirect_ids:
            try:
                redirect_title = id_to_title[redirect_id]
            except KeyError:
                logging.warning("No title found for redirect id: " + redirect_id)
                continue
            print "{0}\t{1}".format(redirect_title, ner)

def main(redirects_file, links_file, pages_file, original_mappings):
    redirects_file = file(redirects_file)
    links_file = file(links_file)
    pages_file = file(pages_file)
    original_mappings = file(original_mappings)

    redirects, links, title_to_id, id_to_title = read_all(redirect_pages_file, page_ids_file, links_file)
    #import cProfile
    #cProfile.run("run(normal_pages, dr_pages, links, title_to_id, id_to_title, is_reverse)")
    run(original_mappings, redirects, links, title_to_id, id_to_title)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s : %(module)s - %(levelname)s - %(message)s")

    if len(sys.argv) != 5:
        sys.stderr.write("Expands a DBpedia->ConLL mapping file by resolving redirects.\n")
        sys.stderr.write("Usage: {0} redirects_file links_file page_file original_mapping_file\n".format(__file__))
        sys.stderr.write("Where: redirects_file is a list of redirect page titles, one per line;")
        sys.stderr.write("       links_file     is the links file from the Wikipedia dump;")
        sys.stderr.write("       pages_file     is the pages file from the Wikipedia dump;")
        sys.exit(1)

    main(sys.argv[1:])

