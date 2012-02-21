## Filters incomplete sentences from a conll file.

from langtools.io.conll2.conll_reader import ConllReader, ConllCallback
from langtools.utils.file_utils import FileWriter

class SentenceFilterCallback(ConllCallback):
    """Filters all incomplete sentences, i.e. those that don't end in a period,
    question mark, etc. and those that don't have a verb in them."""
    def __init__(self):
        self.sentence = []
        self.filters = []

    def addFilter(self, filter):
        """Adds a SentenceFilter to the filter list."""
        if filter is not None and filter not in self.filters:
            self.filters.append(filter)

    def fileStart(self, file_name):
        """Opens output files for the sentences kept, as well as one for each
        filter, where the sentences filtered by that particular filter are
        written."""
        self.kept_file = FileWriter(file_name + '.kept').open()
        self.filtered_files = [FileWriter(file_name + '.f' + str(i)).open()
                               for i in xrange(len(self.filters))]

    def sentenceStart(self):
        self.sentence = []

    def word(self, attributes):
        self.sentence.append(attributes)

    def sentenceEnd(self):
        if len(self.sentence) > 0:
            for i, filter in enumerate(self.filters):
                if not filter.filter(self.sentence):
                    self.filtered_files[i].write(u"\n".join(
                        u"\t".join(word) for word in self.sentence))
                    self.filtered_files[i].write(u"\n\n")
                    return
            self.kept_file.write(u"\n".join(
                u"\t".join(word) for word in self.sentence))
            self.kept_file.write(u"\n\n")

    def fileEnd(self):
        """Closes all the files."""
        self.kept_file.close()
        for ff in self.filtered_files:
            ff.close()

class SentenceFilter(object):
    """Base class for sentence filters."""
    def filter(self, sentence):
        """
        @param sentence is a list of word attributes.
        @return @c True, if the sentence is to be kept; @c False otherwise.
        """
        pass

class TerminalPunctuationFilter(SentenceFilter):
    """Filters sentences that lack terminal punctuation."""
    def __init__(self, lemma_pos=0):
        """@param lemma_pos the position of the lemma field."""
        self.lemma_pos = lemma_pos
        self.punct = set([u'.', u'?', u'!'])

    def filter(self, sentence):
        return sentence[-1][self.lemma_pos] in self.punct

class NoVerbFilter(SentenceFilter):
    """Filters sentences that do not have a verb in them."""
    def __init__(self, pos_pos=1):
        """@param pos_pos the position of the POS field."""
        self.pos_pos = pos_pos

    def filter(self, sentence):
        """Returns @c True, if the sentence contains no verb."""
        for attributes in sentence:
            if attributes[self.pos_pos].startswith(u'V'):
                return True
        return False

if __name__ == '__main__':
    import sys

    sfc = SentenceFilterCallback()
    sfc.addFilter(TerminalPunctuationFilter())
    sfc.addFilter(NoVerbFilter(3))
    ConllReader([sfc]).read(sys.argv[1], "utf-8")

