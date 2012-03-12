"""Converts the NER list to Hungarian (DBpedia uses English URIs)."""

import sys
from optparse import OptionParser

def read_correspondence_map(correspondence_file):
    """Reads the English -> Hungarian article mapping."""
    import gc
    gc.disable()
    ret = {}
    with open(correspondence_file, 'r') as infile:
        for line in infile:
            try:
                orig, others = line.strip().split("\t", 1)
                ret[orig] = others.split("\t")
            except Exception:
                sys.stderr.write("Invalid line: " + line)
    gc.enable()
    return ret

def expand_ner_list(ner_file, correspondence_mapping, keep=False):
    """Converts the NER list according to @p correspondence_mapping."""
    with open(ner_file, 'r') as infile:
        for line in infile:
            try:
                page, cat = line.strip().split("\t", 1)
                if keep:
                    print "{0}\t{1}".format(page, cat)
                new_pages = correspondence_mapping[page]
                for new_page in new_pages:
                    print "{0}\t{1}".format(new_page, cat)
            except KeyError:
                sys.stderr.write("Unknown page " + page + "\n")

if __name__ == '__main__':
    option_parser = OptionParser()
    option_parser.add_option("-k", "--keep", dest="keep",
            action="store_true", default=False,
            help="keeps the English entries")
    options, args = option_parser.parse_args()

    if len(args) != 2:
        sys.stderr.write("Usage: {0} [options] ner_list correspondence_mapping\n\n".format(__file__))
        sys.stderr.write("Expands the NER list with pages from a page correspondence mapping ")
        sys.stderr.write("(e.g. redirects, interlanguage links, etc.). The mapping file is ")
        sys.stderr.write("tab-separated, the first field being a page already in the list, ")
        sys.stderr.write("and the others the new pages to be added with the same categories ")
        sys.stderr.write("as the original.\n\n")
        sys.stderr.write("To see the options, call the script with the -h flag.\n\n")
        sys.exit()

    lang_mapping = read_interlang_map(args[1])
    convert_ner_lang(args[0], lang_mapping, options.keep)

