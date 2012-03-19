"""Extracts the training sentences from the wikipedia pages. A sentence is
considered a training sentence, all links in it are leading to wikipedia pages
whose NE category is known."""

import sys
import re
import os
import os.path
if sys.version_info[0] >= 3:
    from langtools.io.conll2.conll_reader3 import DefaultConllCallback, ConllReader
    from langtools.utils.file_utils3 import *
else:
    from langtools.io.conll2.conll_reader import DefaultConllCallback, ConllReader
    from langtools.utils.file_utils import *
import langtools.utils.cmd_utils
from langtools.utils.cascading_config import CascadingConfigParser
from langtools.utils.useful import all_partitions
from langtools.utils.language_config import LanguageTools

# Functionality needed:
# - from Nothman et al, 2008 (and our ideas, which they blantantly stole in
#   their paper :)):
#   .capitalization (personal titles) (not really needed in Hun?)
# Done:
# - from Nothman et al, 2008 (and our ideas, which they blantantly stole in
#   .link inference (article title, redirects, words in links); trie; digit - cas only
#   .capitalization (first words)
#   .lowercase links: not NEs, if they don't point to a NER.
#   for Hungarian, as LOCs can become lowercased (case?))
# - lowercase link to uppercase LOC (Hun)
# - redirect mapping

class SentenceData(object):
    def __init__(self):
        self.clear_sentence()
        self.clear_statistics()
    
    def clear_statistics(self):
        self.num_words = 0
        self.num_sentences = 0
        self.num_train = 0
    
    def clear_sentence(self):
        self.sentence = []
        self.links_found = 0
        self.links_lost = 0
        self.ner_type = 0
        self.bi = 0
        
    def append(self, attributes):
        """Appends the word and its data to the sentence."""
        s = u'{0}\t{1}'.format(u"\t".join(attributes), self.ner_bi())
#        print "APPEND", s.encode('utf-8')
        self.sentence.append(s)

#    def add_ner(self, ner_type, new=False):
#        was_ner = self.ner_type
#        self.ner_type = ner_type
#        self.bi = 'B' if new else 'I'

    def ner_bi(self):
        """Prints the ner type and also converts 0 to O."""
        return '{0}-{1}'.format(self.bi, self.ner_type) if str(self.ner_type) != '0' else 'O'
    
    def write(self, out):
        """Writes the sentence to the output file."""
        for word in self.sentence:
            out.write(word + '\n')
        out.write('\n')
        self.num_words += len(self.sentence)
        self.num_train += 1
    
    def next_sentence(self):
        """Goes to the next sentence."""
        self.clear_sentence()
        self.num_sentences += 1

class Tries(object):
    """Trie store for the sentence extractor. All full paths have a NER
    category, or UNK, if unknown."""
    def __init__(self, lt):
        """
        @param lt the LanguageTools object.
        """
        self.lt = lt
        self.paths = {}
        self.words = set()

    def add_title(self, title, category):
        """
        Adds the title as an entity. Titles are a bitch because they are
        not parsed.
        """
        par = title.rfind('(')
        if par != -1 and par != 0:
            title = title[par - 1:]
        words = self.lt.word_tokenize(title)
        self.add_anchor(words, category)

    def add_anchor(self, words, category):
        tpl, old_category = self.get_category(words)
        if old_category is None:
            self.add_path(tpl, category)
            if category == 'PER':
                self.add_path([tpl[0]], category)
                self.add_path([tpl[-1]], category)
        elif old_category != category:
            self.paths[tpl] = 'UNK'

    def add_path(self, words, category):
        """Adds a path (words of an entity)."""
        if type(words) == list:
            words = tuple(words)
        for word in words:
            self.words.add(word)
        self.paths[words] = category

    def get_category(self, words):
        """Returns the word tuple and its category."""
        if type(words[0]) == list:
            # Last words: raw or lemma
            words_raw = [word[NERTrainingCallback.RAW].lower() for word in words]
            tpl1 = tuple(words_raw)
            tpl2 = tuple(words_raw[:-1] + [words[-1][NERTrainingCallback.LEMMA].lower()])
            try:
                return tpl1, self.paths[tpl1]
            except KeyError:
                return tpl2, self.paths.get(tpl2, None)
        else:
            tpl = tuple(words)
            return tpl, self.paths.get(tpl, None)  # lower() ?

    def clear(self):
        """Clears the trie."""
        self.paths = {}
        self.words = set()

class NERTrainingCallback(DefaultConllCallback):
    """The callback that collects sentences that can serve as a training corpus.
    A sentence is eligible for inclusion in the training set if it contains at
    least one link to a wiki page whose category is known and no links to pages
    whose category is unknown. Sentences that have title-case words (a capital
    letter followed by lowercase letters) in them are skipped as well.
    Only the 'body' field is checked for training sentences. The title
    is used in another way: if the title-case words in the candidate sentence
    are all included in the title as well, the sentence can still be added to
    the training set.
    """
    NO_LINK, NER_LINK, NNP_LINK = xrange(3)
    # The field indices
    RAW, STYLE, LINK, POS, LEMMA = xrange(5)

    LINK_PATTERN = re.compile('^(?:w[:])(?:[a-zA-Z][a-z][A-Z]:)?(.+)$')
    
    def __init__(self, trie, keep_discarded=False, outs=None):
        """
        Initializes the callback. If specified, the training sentences are
        written to @c outs; otherwise they are written to a separate output
        file for each input file called <input_file_name>.ner.
        
        @param trie the trie (not) that stores links seen in the page so far.
        @param keep_discarded if @c True, the discarded sentences will be
                              written to a file called <input_file_name>.discarded.
        @param outs the output stream to write the data to.
        """
        DefaultConllCallback.__init__(self)
        self._sent = SentenceData()
        self._title = []         # title of the current page
        self._cat = None         # category of the current page
        self._gold_map = {}      # page: category
        self._redirect_map = {}  # page: redirects
        self._trie = trie        # the NERs mentioned on the page
        self._mode = NERTrainingCallback.NO_LINK  # state machine state
        self._keep_discarded = keep_discarded

        self._out = None
        self._discarded = None
        
    def read_gold(self, gold_file):
        """Reads the gold file and fills the {page -> category} map from them.
        Old values are not deleted."""
        gold = FileReader(gold_file, 'utf-8').open()
        for line in gold:
            kv = line.strip().split("\t")
            if len(kv) == 2:
                self._gold_map[kv[0].lower()] = kv[1]
        gold.close()
        # TODO: logging
        #print len(self._gold_map)

    def read_redirects(self, redirects_file):
        """Reads the redirects file and fills the {page -> redirect} map from
        it. Only pages in the gold map are retained."""
        with FileReader(redirects_file, 'utf-8').open() as redirects: 
            import gc
            gc.disable()
            for line in redirects:
                kv = line.strip().split("\t")
                if len(kv) >= 2 and kv[0].lower() in self._gold_map:
                    redirs = self._redirect_map.get(kv[0].lower(), [])
                    redirs.extend(l.lower() for l in kv[1:])
                    self._redirect_map[kv[0].lower()] = redirs
            gc.enable()

    # ConllCallback methods
    def fileStart(self, file_name):
        """Opens the output file."""
        DefaultConllCallback.fileStart(self, file_name)
        self._out = FileWriter(file_name + '.ner').open()
        if self._keep_discarded:
            self._discarded = FileWriter(file_name + '.discarded').open()
            
    def fieldStart(self, field):
        DefaultConllCallback.fieldStart(self, field.lower())
        # We get the category from the title, and also need the words it
        # contains before the last '(' (after which it only contains Wikipedia-
        # specific information, such as disambiguation, etc.) for the link
        # inference trie
        if (self.cc_field.lower() == 'title'):
            self._title = []
            self._title_pars = self.cc_title.count('(')
            if self._title_pars == 0:
                self._title_pars = 1

            self._trie.clear()
            self._cat = self._gold_map.get(self.cc_title, None)
            if self._cat is not None:
                self._trie.add_title(self.cc_title, self._cat)
                self.__add_redirects(self.cc_title, self._cat)
        elif self.cc_field.lower() == 'body':
            self.first = True
            self._mode = NERTrainingCallback.NO_LINK
            self.tmp = []
    
    def word(self, attributes):
        """Records the words in a C{SentenceData} object."""
        if not self.cc_redirect:
            if self.cc_field.lower() == 'title':
                if attributes[NERTrainingCallback.RAW] == '(':
                    self._title_pars -= 1
                if self._title_pars > 0:
                    self._title.append(attributes[NERTrainingCallback.LEMMA])
            elif self.cc_field.lower() == 'body':

                if len(attributes) >= 5:
                    # Redirect check
                    if self.first:
                        self.first = False
                        if attributes[0].lower() == 'redirect':
                            self.cc_redirect = True
                            return

                    # State machine part
                    #print "ATTR", attributes
                    if self._mode == NERTrainingCallback.NER_LINK:
                        if attributes[1] == 'B-link':
#                            print "NER -> NER"
                            self.__add_tmp()
                            self.__start_link(attributes)
                        elif attributes[1] == 'I-link':
#                            print "NER -> sNER"
                            self._sent.bi = 'I'
                        else:
#                            print "NER -> NO/NNP"
                            self.__add_tmp()
                            self._sent.ner_type = 0
                            if self.__is_NNP(attributes):
                                self._mode = NERTrainingCallback.NNP_LINK
                            else:
                                self._mode = NERTrainingCallback.NO_LINK
                    elif self._mode == NERTrainingCallback.NNP_LINK:
                        if attributes[1] == 'B-link':
#                            print "NNP -> NER"
                            self.__add_tmp()
                            self.__start_link(attributes)
                        elif not self.__is_NNP(attributes):
#                            print "NNP -> NO"
                            self.__add_tmp()
                            self._mode = NERTrainingCallback.NO_LINK
                            self._sent.ner_type = 0
#                        else:
#                            print "NNP -> NNP"
                    elif self._mode == NERTrainingCallback.NO_LINK:
                        if attributes[1] == 'B-link':
#                            print "NO -> NER"
                            self.__add_tmp()
                            self.__start_link(attributes)
                        elif self.__is_NNP(attributes):
#                            print "NO -> NNP"
                            self.__add_tmp()
                            self._mode = NERTrainingCallback.NNP_LINK
#                        else:
#                            print "NO -> NO"

                    self.tmp.append(attributes)
                else:
                    # TODO: logging
                    sys.stderr.write("Illegal word record [{0}] in page {1}\n".format(
                        u','.join(attributes).encode('utf-8'),
                        self.cc_title.encode('utf-8')))
    
    def __add_tmp(self):
        if len(self.tmp) == 0:
            return

        print "TMP", self.tmp, self._sent.ner_type
        """Adds the temporary chunk to the output sentence."""
        if self._mode == NERTrainingCallback.NER_LINK:
            for i, attributes in enumerate(self.tmp):
                if i == 0:
                    self._sent.bi = 'B'
                else:
                    self._sent.bi = 'I'
                self._sent.append(attributes)
            self._trie.add_anchor(self.tmp, self._sent.ner_type)
        elif self._mode == NERTrainingCallback.NO_LINK:
            for attributes in self.tmp:
                self._sent.append(attributes)
        elif self._mode == NERTrainingCallback.NNP_LINK:
#            print "TRIE", self._trie.paths
            sentence_start_non_nnp = False
            for partition in all_partitions(self.tmp):
                categories = [self._trie.get_category(part)[1] for part in partition]
#                print "PC", partition, categories
                for i, category in enumerate(categories):
                    if category is None or category is 'UNK':
                        # Invalid NNP, UNLESS the first word is sentence starter
                        if (len(self._sent.sentence) == 0 and i == 0 and
                            len(partition[i]) == 1 and
                            not self.__has_noun(partition[i])):
                            sentence_start_non_nnp = True
                        else:
                            break
                else:
                    for i, part in enumerate(partition):
                        if i == 0 and sentence_start_non_nnp:
                            self._sent.ner_type = 0
                            for word in part:
                                self._sent.append(word)
                        else:
                            self._sent.ner_type = categories[i]
                            was_B = False
                            for word in part:
                                if not was_B:
                                    self._sent.bi = 'B'
                                    was_B = True
                                else:
                                    self._sent.bi = 'I'
                                self._sent.append(word)
                    break
            else:
#                print "NO NNP FOUND!"
                self._sent.ner_type = 'UNK'
                for attributes in self.tmp:
                    self._sent.append(attributes)
                self._sent.links_lost += 1
        self.tmp = []

    def __has_noun(self, chunk):
        """Returns @c True, if there is at least one noun in chunk."""
        return any(attr[NERTrainingCallback.POS].startswith(u'NOUN')
                   for attr in chunk)

    def __get_gold(self, link):
        return self._gold_map.get(link.lower(), 0)

    def __add_redirects(self, link, category):
        """Adds the redirects of a link to the trie."""
        for redirect in self._redirect_map.get(link, []):
            self._trie.add_title(redirect, category)

    def __start_link(self, attributes):
        """Temporary, to refactor."""
        self._sent.ner_type = self.__get_gold(attributes[NERTrainingCallback.LINK])
        self._mode = NERTrainingCallback.NER_LINK
        self._sent.bi = 'B'
        if self._sent.ner_type != 0:
#            print "LINK", attributes, self._sent.ner_type
            self._sent.links_found += 1
            self.__add_redirects(attributes[NERTrainingCallback.LINK], self._sent.ner_type)
            # Hungarian: budapesti is not LOC (not even NER)
            if (self._sent.ner_type == 'LOC' and
                attributes[NERTrainingCallback.RAW][0].islower()):
                self._sent.ner_type = 0
 #               print "NOT LOC", attributes
        else:
 #           print "LINK LOST", attributes
            # Lowercase links point to common nouns
            if attributes[NERTrainingCallback.RAW][0].islower():
                print "HAHA", attributes
                self._sent.ner_type = 0
            else:
                self._sent.ner_type = 'UNK'
                self._sent.links_lost += 1

    def __is_NNP(self, attributes):
        """Decides if word is NNP. Also, if a title-cased word occurs in the
        title as well, sets the ner type to the current page's type (if any)."""
        if attributes[NERTrainingCallback.LEMMA].isdigit():
            if (attributes[NERTrainingCallback.LEMMA] in self._trie.words and
                'CAS' in attributes[NERTrainingCallback.POS]):
                return True
            else:
                return False
        else:
#            if len(self._sent.sentence) > 0:
                # TODO: POS?
                # TODO: maybe_NNP
#                return False  # TODO: sentences CAN start w/ entities
            if attributes[NERTrainingCallback.RAW][0].isupper():
#            if (attributes[NERTrainingCallback.RAW].istitle() or
#                  attributes[NERTrainingCallback.RAW].isupper()):
                return True
    
    def sentenceEnd(self):
        """If the sentence contains links only to entities whose types are
        known, it is written to the output file."""
        if self.cc_field.lower() == 'body':
#            print "SEND"
            self.__add_tmp()
            if self._sent.links_lost == 0:
#                print "NO LOST FOUND"
                self._sent.write(self._out)
            elif self._keep_discarded:
#                print "DISCARDED + LOST FOUND"
                self._sent.write(self._discarded)
            self._sent.next_sentence()
    
    def fileEnd(self):
        """Closes the output file."""
        if self._sent.num_train > 0:
            sys.stderr.write("Written {0} sentences out of {1}, with avg length = {2} for file {3}.\n".format(
                    self._sent.num_train, self._sent.num_sentences,
                    float(self._sent.num_words) / self._sent.num_train,
                    self.cc_file))
        self._sent.clear_statistics()
        DefaultConllCallback.fileEnd(self)
        self._out.close()
        self._out = None
        if self._discarded is not None:
            self._discarded.close()
            self._discarded = None

if __name__ == '__main__':
    from optparse import OptionParser

    option_parser = OptionParser()
    option_parser.add_option("-l", "--language", dest="language",
            help="the Wikipedia language code. Default is en.", default="en")
    option_parser.add_option("-r", "--redirects", dest="redirects",
            help="normal -> redirect page mapping.", default=None)
    option_parser.add_option("-d", "--discarded", dest="discarded",
            action="store_true", default=False,
            help="also generate .discarded files.")
    options, args = option_parser.parse_args()

    if len(args) < 3:
        print('Creates NER training corpus from Wikipedia pages.\n')
        print('Usage: {0} [options] config_file gold_file input_files+')
        print('       config_file: the configuration file. Must contain a section' +
              ' called <language option>-ner')
        print('       gold_file: the entity -> NER category mapping file\n')
        sys.exit(1)

    #config_parser = CascadingConfigParser(args[0])

#    config = dict(config_parser.items(options.language + '-ner'))

    lt = LanguageTools(args[0], options.language)
    trie = Tries(lt)
    ntc = NERTrainingCallback(trie, options.discarded)
    ntc.read_gold(args[1])
    if options.redirects is not None:
        ntc.read_redirects(options.redirects)
    
    cr = ConllReader([ntc])
    for wiki_file in args[2:]:
        cr.read(wiki_file)

