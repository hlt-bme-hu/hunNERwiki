"""Reads the DBpedia ontology and extracts the classes from it. Also contains
general OWL processing functions."""

import sys
import re
import copy
import xml.sax.handler

class OwlClassHierarchy(xml.sax.handler.ContentHandler):
    URI_PATTERN = re.compile(r'http:.*/(.+)')
    EMPTY_SET   = set()

    """Parses OWL xml ontologies and extracts all class (of type owl:Class)
    with their respective superclasses (the rdfs:subClassOf property)."""
    def __init__(self, owl_file=None):
        """If @p owl_file is not @c None, parses it."""
        self.tree = {'owl#Thing': set()}
        self.cls = None
        self.super_cls = []
        self.sorted = None
        self.isa_map = None
        if owl_file is not None:
            parser = xml.sax.make_parser()
            parser.setContentHandler(self)
            parser.parse(owl_file)
            del parser

    def startElement(self, name, attrs):
        if name == 'owl:Class':
            uri = attrs.get('rdf:about')
            if uri is not None:
                self.cls = OwlClassHierarchy._strip_uri(uri)
        elif name == 'rdfs:subClassOf':
            uri = attrs.get('rdf:resource')
            if self.cls is not None and uri is not None:
                self.super_cls.append(OwlClassHierarchy._strip_uri(uri))

    def endElement(self, name):
        if name == 'owl:Class':
            self.tree[self.cls] = set(self.super_cls)
            self.cls = None
            self.super_cls = []

    def create_isa_map(self):
        """Creates a fast IS-A map. Should be used only if the number of
        classes is small."""
        self.isa_map = {}
        self.get_sorted()
        for cat in sorted(self.sorted.keys(), key=self.sorted.get):
            parents = self.tree[cat]
            ancestors = set(parents)
            for parent in parents:
                ancestors |= self.isa_map.get(parent, OwlClassHierarchy.EMPTY_SET)
            if len(ancestors) > 0:
                self.isa_map[cat] = ancestors

    def is_a(self, descendant, ancestor):
        """Returns @c True, if @p descendant IS-A @p ancestor."""
        if self.isa_map is not None:
            return ancestor in self.isa_map.get(descendant, OwlClassHierarchy.EMPTY_SET)
        else:
            return self._is_a(descendant, ancestor, descendant)

    def _is_a(self, descendant, ancestor, current):
        """Recursive helper method for is_a."""
        parents = self.tree.get(current)
        if parents is None:
            return False
        if ancestor in parents:
            return True
        else:
            for parent in parents:
                if self._is_a(descendant, ancestor, parent):
                    return True
            return False

    def get_sorted(self):
        """Returns the classes sorted according to cmp. The result is returned
        not as a list, but as a {class: index} dictionary."""
        if self.sorted is None:  # Half-assed cache
            # We presume the following:
            # - all classes are used as keys
            # - there are no cycles in the type hierarchy
            self.sorted = []

            data = copy.deepcopy(self.tree)
            # Topological sort algorithm by Paddy McCarthy, taken from
            # http://code.activestate.com/recipes/577413-topological-sort/
            for k, v in data.items():
                v.discard(k) # Ignore self dependencies
                extra_items_in_deps = reduce(set.union, data.values()) - set(data.keys())
                data.update({item:set() for item in extra_items_in_deps})
            while True:
                ordered = set(item for item, dep in data.items() if not dep)
                if not ordered:
                    break
                self.sorted += list(ordered)
                data = {item: (dep - ordered) for item, dep in data.items()
                        if item not in ordered}
            assert not data, "A cyclic dependency exists amongst %r".format(data)

            self.sorted = dict((t[1], t[0]) for t in enumerate(self.sorted))
        return self.sorted

    @staticmethod
    def _strip_uri(uri):
        m = OwlClassHierarchy.URI_PATTERN.match(uri)
        return m.group(1) if m is not None else uri

    def __str__(self):
        lines = ['{0}: {1}'.format(key, ','.join(value)) for key, value in self.tree.iteritems()]
        return "\n".join(lines)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "Usage: {0} <owl ontology>".format(__file__)
        sys.exit()

    handler = OwlClassHierarchy(sys.argv[1])
#    print handler.get_sorted()
    handler.create_isa_map()
    print handler.is_a('University', 'Organisation')

