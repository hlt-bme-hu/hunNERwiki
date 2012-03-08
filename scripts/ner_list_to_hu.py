"""Converts the NER list to Hungarian (DBpedia uses English URIs)."""

import sys

def read_interlang_map(interlang_file):
    """Reads the English -> Hungarian article mapping."""
    import gc
    gc.disable()
    ret = {}
    with open(interlang_file, 'r') as infile:
        for line in infile:
            try:
                en, hu = line.strip().split("\t")
                ret[en] = hu
            except Exception:
                sys.stderr.write("Invalid line: " + line)
    gc.enable()
    return ret

def convert_ner_lang(ner_file, lang_mapping):
    """Converts the NER list according to @p lang_mapping."""
    with open(ner_file, 'r') as infile:
        for line in infile:
            try:
                page, cat = line.strip().split("\t")
                hu_page = lang_mapping[page]
                print "{0}\t{1}".format(hu_page, cat)
            except KeyError:
                sys.stderr.write("Unknown page " + page)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.stderr.write("Usage: {0} ner_list language_mapping\n\n".format(__file__))
        sys.exit()

    lang_mapping = read_interlang_map(sys.argv[2])
    convert_ner_lang(sys.argv[1], lang_mapping)

