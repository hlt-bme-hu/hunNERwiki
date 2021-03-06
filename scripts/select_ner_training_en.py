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
from langtools.utils import misc
from trie import *

# Functionality needed:
# - from Nothman et al, 2008 (and our ideas, which they blantantly stole in
#   their paper :)):
#   .lowercase links: drop / analyse incoming link capitalization
# Done:
# - from Nothman et al, 2008 (and our ideas, which they blantantly stole in
#   their paper :)):
#   .capitalization (first words, dates)
#   .link inference (article title, redirects, words in links)
#   .adjectival forms (nationalities) - English only
#   .capitalization (personal titles)
# - redirect mapping

__zero_ner_types = set([0, '0', 'O'])
def zero_ner_type():
    return 'O'
def is_ner_type_zero(ner):
    return ner in __zero_ner_types

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
        self.sentence.append(u'{0}\t{1}'.format(
                u"\t".join(attributes), self.ner_bi()))

#    def add_ner(self, ner_type, new=False):
#        was_ner = self.ner_type
#        self.ner_type = ner_type
#        self.bi = 'B' if new else 'I'

    def ner_bi(self):
        """Prints the ner type and also converts 0 to O."""
        return '{0}-{1}'.format(self.bi, self.ner_type) if not is_ner_type_zero(self.ner_type) else zero_ner_type()
    
    def write(self, out):
        """Writes the sentence to the output file."""
        for word in self.sentence:
            #out.write(word + '\n')
            out.write(word.encode('iso-8859-2', 'xmlcharrefreplace') + '\n')
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
        self.words = set()     # The words that occur in paths
        self.prefixes = set()  # Prefixes for the entries in paths

    def add_title(self, title, category):
        """
        Adds the title as an entity. Titles are a bitch because they are
        not parsed.
        """
        par = title.rfind('(')
        if par != -1 and par != 0:
            title = title[0 : par]
        words = self.lt.word_tokenize(title)
        self.add_anchor(words, category)

    def add_anchor(self, words, category):
        tpl, old_category = self.get_category_or_none(words)
        if old_category is None:
            self.add_path(tpl, category)
            if category == 'PER':
                self.add_path([tpl[0]], category)
                self.add_path([tpl[-1]], category)
        elif old_category != category:
            self.paths[tpl] = 'UNK'

    def add_path(self, words, category):
        """Adds a path (words of an entity)."""
        words = tuple(word.lower() for word in words)
        for word in words:
            self.words.add(word)
        for i in xrange(len(words)):
            self.prefixes.add(tuple(words[0 : i + 1]))
        self.paths[words] = category

    def get_category_or_none(self, words):
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

    def get_category(self, words):
        tpl, cat = self.get_category_or_none(words)
        if cat is None:
            cat = 'UNK'
        return tpl, cat

    def is_prefix(self, words, word):
        """Checks if words + word is a prefix to an entity."""
        # Last words: raw or lemma
        words_raw = [token[NERTrainingCallback.RAW].lower() for token in words]
        tpl1 = tuple(words_raw + [word[NERTrainingCallback.RAW].lower()])
        tpl2 = tuple(words_raw + [word[NERTrainingCallback.LEMMA].lower()])
        return tpl1 in self.prefixes or tpl2 in self.prefixes

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
    months = set(['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November',
                  'December'])
    nnps = set(['NNP', 'NNPS'])
    
    def __init__(self, trie, keep_discarded=False, keep_filtered=False, outs=None):
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
        self._title = []
        self._cat = None
        self._gold_map = {}
        self._redirect_map = {}  # page: redirects
        self._trie = trie        # the NERs mentioned on the page
        self._mode = NERTrainingCallback.NO_LINK  # state machine state
        self._punct = set(u'.?!:')  # Sentences should end with one of these
        self._link_punct = set(u'.?!:,;')  # To strip from the end of links
        self._keep_discarded = keep_discarded
        self._keep_filtered = keep_filtered

        self._out = None
        self._discarded = None
        self._filtered = None

        self._quot = misc.quotationMarks | misc.brackets
        self._titles = None
        
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
                    redirs = self._redirect_map.get(kv[0].lower(), set())
                    for l in kv[1:]:
                        redirs.add(l.lower())
#                    redirs.add(l.lower() for l in kv[1:])
                    self._redirect_map[kv[0].lower()] = redirs
            gc.enable()

    def read_titles(self, lt, titles_file):
        """
        Reads the titles form a file and inserts them into a trie.
        @param lt the languagetools object used for tokenization.
        """
        trie = Trie()
        with FileReader(titles_file, 'utf-8').open() as titles:
            for line in titles:
                line = line.strip().lower()
                if len(line) == 0:
                    continue
                trie.add(lt.word_tokenize(line))
        if len(trie) > 0:
            self._titles = trie

    # ConllCallback methods
    def fileStart(self, file_name):
        """Opens the output file."""
        DefaultConllCallback.fileStart(self, file_name)
        self._out = open(file_name + '.ner', 'w')
        if self._keep_discarded:
            self._discarded = open(file_name + '.discarded', 'w')
        if self._keep_filtered:
            self._filtered = open(file_name + '.filtered', 'w')
            
    def fieldStart(self, field):
#        print "NERTrainingCallback:fieldStart"
        DefaultConllCallback.fieldStart(self, field.lower())
        # We get the category from the title, and also need the words it
        # contains before the last '(' (after which it only contains Wikipedia-
        # specific information, such as disambiguation, etc.) for the link
        # inference trie
        if (self.cc_field.lower() == 'title'):
            print "PAGE", self.cc_title.encode('utf-8')
            self._title = []
            self._title_pars = self.cc_title.count('(')
            if self._title_pars == 0:
                self._title_pars = 1

            self._trie.clear()
            self._cat = self._gold_map.get(self.cc_title.lower(), None)
            if self._cat is not None:
                self._trie.add_title(self.cc_title, self._cat)
                self.__add_redirects(self.cc_title, self._cat)
        elif self.cc_field.lower() == 'body':
            self.first = True
            self._mode = NERTrainingCallback.NO_LINK
            self.tmp = []
            self.sentence_words = []
    
    def word(self, attributes):
        """
        Puts all tokens to self.sentence_words, so that we can do sentence-
        level checks first.
        """
#        print "NERTrainingCallback:word", attributes
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

                    # Real work part
                    self.sentence_words.append(attributes)
                else:
                    # TODO: logging
                    sys.stderr.write("Illegal word record [{0}] in page {1}\n".format(
                        u','.join(attributes).encode('utf-8'),
                        self.cc_title.encode('utf-8')))

    def word2(self, attributes):
        """
        Records the words in a C{SentenceData} object. Called by sentenceEnd
        in the same way word would be called by the reader.
        """
#        print "NERTrainingCallback:word2", attributes
        sys.stdout.flush()
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
                self._sent.ner_type = zero_ner_type()
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
                if not self.__is_NNP_prefix(attributes):
#                            print "NNP -> NO"
                    self.__add_tmp()
                    self._mode = NERTrainingCallback.NO_LINK
                    self._sent.ner_type = zero_ner_type()
#            elif len(self.tmp) == 8:  # Too long
#                self.__add_tmp()
#                self._mode = NERTrainingCallback.NO_LINK
#                self._sent.ner_type = 0
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

    def __is_NNP_prefix(self, attributes):
        """
        Trie functionality... maybe I should have implemented it correctly.
        Anyway, this method is here to handle not titlecase words in
        a NE (Harry Potter and the Deathly Hollows). If such words are met,
        but the chunk read so far is a prefix to a known entity, we do
        not throw it away just then.
        """
        for i in xrange(len(self.tmp)):
            if self._trie.is_prefix(self.tmp[i:], attributes):
                return True
        return False

    def __title_in_entity(self, entity):
        """
        Returns the length of the title the entity has, if any. The title is
        assumed to precede the entity.
        """
        if self._titles is None:
            return 0
        lemma_entity = [word[NERTrainingCallback.LEMMA].lower() for word in entity]
        length, valid = self._titles.get_length(lemma_entity)
        return length if valid else 0

    def __partition_candidate(self, candidate, ner_type):
        """
        Partitions the candidate into personal title (PER and UNK), entity and
        punctuation parts. Returns the two indexing partitioning the candidate.
        """
        # The link may end with punctuation marks -- let's remove them!
        begin, last = 0, len(candidate)
        for token in reversed(candidate):
            if token[NERTrainingCallback.LEMMA] in self._link_punct:
                last -= 1
            else:
                break

        if last != 0:
            if ner_type == 'PER' or ner_type == 'UNK':
                title_length = self.__title_in_entity(candidate[0 : last])
                if title_length > 0:
                    begin = title_length

        return begin, last

    def __add_tmp(self):
#        print "NERTrainingCallback:__add_tmp"
        if len(self.tmp) == 0:
            return

#        print "TMP", self.tmp, self._sent.ner_type
        """Adds the temporary chunk to the output sentence."""
        if self._mode == NERTrainingCallback.NER_LINK:
            begin, last = self.__partition_candidate(self.tmp, self._sent.ner_type)

            if last != 0:
                # Add the title as regular text
                if begin != 0:
                    tmp_type = self._sent.ner_type
                    self._sent.ner_type = zero_ner_type()
                    for attributes in self.tmp[0 : begin]:
                        self._sent.append(attributes)
                    self._sent.ner_type = tmp_type

                # Add the real entity part
                if begin != last:
                    # If the anchor link is an adjective, and the last word does not
                    # occur in the link target, then it is a derivative form of the
                    # entity and must be a MISC according to ConLL guidelines
                    if (self.tmp[last - 1][NERTrainingCallback.POS].startswith(u'J')
                        and not self.tmp[last - 1][NERTrainingCallback.RAW].lower()
                            in self.tmp[last - 1][NERTrainingCallback.LINK].lower()
                        and self._sent.ner_type != 'UNK'
                        and self._sent.ner_type != zero_ner_type()):
                        sys.stderr.write("Adj entity: {0}\n".format(self.tmp[0 : last]))
                        self._sent.ner_type = 'MISC'
                    # Add the link stripped of punctuation marks
                    for i, attributes in enumerate(self.tmp[begin : last]):
                        if i == 0:
                            self._sent.bi = 'B'
                        else:
                            self._sent.bi = 'I'
                        self._sent.append(attributes)
                    self._trie.add_anchor(self.tmp[begin : last], self._sent.ner_type)

                # Unknown link: we must throw the sentence away
                if self._sent.ner_type == 'UNK':
                    self._sent.links_lost += 1

            # And the rest as regular text
            self._sent.ner_type = zero_ner_type()
            for attributes in self.tmp[last:]:
                self._sent.append(attributes)

        elif self._mode == NERTrainingCallback.NO_LINK:
            for attributes in self.tmp:
                self._sent.append(attributes)
        elif self._mode == NERTrainingCallback.NNP_LINK:
#            print "NNP", self.tmp, self._sent.ner_type, len(self.tmp)
#            sys.stdout.flush()
#            print "TRIE", self._trie.paths

            if len(self.tmp) <= 8:
                sentence_start_non_nnp = False
                for partition in all_partitions(self.tmp):
                    categories = [self._trie.get_category(part)[1] for part in partition]
#                    print "PC", partition, categories
                    for i, category in enumerate(categories):
                        if category == 'UNK':
                            # Invalid NNP, UNLESS the first word is sentence starter
                            if (len(self._sent.sentence) == 0 and i == 0 and
                                len(partition[i]) == 1 and
                                not self.__has_noun(partition[i])):
                                sentence_start_non_nnp = True
                            else:
                                begin, last = self.__partition_candidate(partition[i], category)
                                if begin != last:
                                    category = self._trie.get_category(partition[i][begin : last])[1]
                                    if category == 'UNK' or (begin > 0 and category != 'PER'):
                                        break
                    else:
                        for i, part in enumerate(partition):
                            # At the beginning of a sentence, and the first word
                            # is not an NN(P)
                            if i == 0 and sentence_start_non_nnp:
                                self._sent.ner_type = zero_ner_type()
                                for word in part:
                                    self._sent.append(word)
                            # The rest of the partitions
                            else:
                                self._sent.ner_type = categories[i]
                                begin, last = self.__partition_candidate(part, category)

                                # Add the title as regular text
                                if begin != 0:
                                    self._sent.ner_type = zero_ner_type()
                                    for attributes in self.tmp[0 : begin]:
                                        self._sent.append(attributes)

                                # Add the real entity part
                                if begin != last:
                                    link, category = self._trie.get_category(partition[i][begin : last])
                                    link = u" ".join(link)
                                    # If the anchor link is an adjective, and the last word does not
                                    # occur in the link target, then it is a derivative form of the
                                    # entity and must be a MISC according to ConLL guidelines
                                    if (part[last - 1][NERTrainingCallback.POS].startswith(u'J')
                                        and not part[last - 1][NERTrainingCallback.RAW].lower()
                                            in link.lower()
                                        and category != 'UNK'):
                                        sys.stderr.write("Adj entity: {0}\n".format(self.tmp[0 : last]))
                                        category = 'MISC'

                                    self._sent.ner_type = category
                                    # Add the link stripped of punctuation marks
                                    for i, attributes in enumerate(part[begin : last]):
                                        if i == 0:
                                            self._sent.bi = 'B'
                                        else:
                                            self._sent.bi = 'I'
                                        self._sent.append(attributes)

                                    if self._sent.ner_type == 'UNK':
                                        self._sent.links_lost += 1

                                # And the rest as regular text
                                self._sent.ner_type = zero_ner_type()
                                for attributes in self.tmp[last:]:
                                    self._sent.append(attributes)

                        # We are done, let's break
                        break
                else:  # for
                    self.__unknown_nnp_link()
            else:  # if len <= 8
                self.__unknown_nnp_link()

        self.tmp = []

    def __unknown_nnp_link(self):
#        print "NO NNP FOUND!"
        self._sent.ner_type = 'UNK'
        for attributes in self.tmp:
            self._sent.append(attributes)
        self._sent.links_lost += 1

    def __has_noun(self, chunk):
        """Returns @c True, if there is at least one noun in chunk."""
#        print "NERTrainingCallback:__has_noun"
        return any(attr[NERTrainingCallback.POS].startswith(u'NOUN')
                   for attr in chunk)

    def __get_gold(self, link):
#        print "NERTrainingCallback:__get_gold"
        return self._gold_map.get(link.lower(), 'UNK')

    def __add_redirects(self, link, category):
        """Adds the redirects of a link to the trie."""
#        print "NERTrainingCallback:__add_redirects", link.encode('utf-8'), category
        if category != 0 and category != '0':
            for redirect in self._redirect_map.get(link.lower(), []):
                self._trie.add_title(redirect, category)

    def __start_link(self, attributes):
        """Temporary, to refactor."""
#        print "NERTrainingCallback:__start_link", attributes
        self._sent.ner_type = self.__get_gold(attributes[NERTrainingCallback.LINK])
        self._mode = NERTrainingCallback.NER_LINK
        self._sent.bi = 'B'

        # Lowercase links point to common nouns, or are non-NER pointers, such
        # as "azonos ci'mu""
        if attributes[NERTrainingCallback.RAW][0].islower():
            print "ISLOWER", attributes, self._sent.ner_type
            # All lower-case links are of type 0
            self._sent.ner_type = zero_ner_type()

        if not is_ner_type_zero(self._sent.ner_type):
#            print "LINK", attributes, self._sent.ner_type
            if self._sent.ner_type != 'UNK':
                self._sent.links_found += 1
            self.__add_redirects(attributes[NERTrainingCallback.LINK], self._sent.ner_type)

    def __is_NNP(self, attributes):
        """Decides if word is NNP. Also, if a title-cased word occurs in the
        title as well, sets the ner type to the current page's type (if any)."""
        if attributes[NERTrainingCallback.LEMMA].isdigit():
            if attributes[NERTrainingCallback.LEMMA] in self._trie.words:
                # Not necessarily -- this might be BAD
                return True
            else:
                return False
        else:
            if not attributes[NERTrainingCallback.LEMMA][0].isupper():
                return False
            elif attributes[NERTrainingCallback.LEMMA] in NERTrainingCallback.months:
                # TODO add trie too
                return False
            # TODO: solve this: use two passes.
            elif attributes[NERTrainingCallback.POS] in NERTrainingCallback.nnps:
                return True
            else:
                return False

    def sentenceEnd(self):
        """If the sentence contains links only to entities whose types are
        known, it is written to the output file."""
#        print "NERTrainingCallback:sentenceEnd"
        if self.cc_field.lower() == 'body':
            if len(self.sentence_words) > 1:
                if (self.__ends_in_punct() and self.__starts_with_uppercase() and
                    self.__not_enumeration()):
                    for attributes in self.sentence_words:
                        self.word2(attributes)
        #            print "SEND"
                    self.__add_tmp()
                    if self._sent.links_lost == 0:
        #                print "NO LOST FOUND"
                        self._sent.write(self._out)
                    elif self._keep_discarded:
        #                print "DISCARDED + LOST FOUND"
                        self._sent.write(self._discarded)
                    self._sent.next_sentence()
                elif self._keep_filtered:
    #                print "FILTERED"
                    for attributes in self.sentence_words:
                        self._filtered.write(u"\t".join(attributes).encode('iso-8859-2', 'xmlcharrefreplace') + "\n")
                    self._filtered.write("\n")
            self.sentence_words = []

    def __not_enumeration(self):
        """
        Returns @c True, if the current sentence is not just a number and a dot.
        """
        return not (len(self.sentence_words) == 2 and
                    self.sentence_words[0][NERTrainingCallback.LEMMA].isdigit() and
                    self.sentence_words[1][NERTrainingCallback.LEMMA] == '.')

    def __starts_with_uppercase(self):
        """
        Returns @c True, if the current sentence starts with an uppercase letter
        or a digit.
        """
        for token in self.sentence_words:
            if (token[NERTrainingCallback.RAW][0].isdigit() or 
                token[NERTrainingCallback.RAW][0].isupper()):
                return True
            elif token[NERTrainingCallback.LEMMA] in self._quot:
                continue
            else:
                break
        return False
        
    def __ends_in_punct(self):
        """
        Returns @c True, if the current sentence is valid, i.e. ends with one
        of the usual sentence-ending punctuation marks.
        """
        for token in reversed(self.sentence_words):
            if (token[NERTrainingCallback.LEMMA] in self._punct or 
                token[NERTrainingCallback.LEMMA][-1] == u'.'):
                return True
            elif token[NERTrainingCallback.LEMMA] in self._quot:
                continue
            else:
                break
        return False
    
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
        if self._filtered is not None:
            self._filtered.close()
            self._filtered = None

if __name__ == '__main__':
    from optparse import OptionParser

    option_parser = OptionParser()
    option_parser.add_option("-l", "--language", dest="language",
            help="the Wikipedia language code. Default is en.", default="en")
    option_parser.add_option("-r", "--redirects", dest="redirects",
            action="append",
            help="normal -> redirect page mapping.", default=None)
    option_parser.add_option("-t", "--titles", dest="titles",
            action="append",
            help="list of personal titles.", default=None)
    option_parser.add_option("-d", "--discarded", dest="discarded",
            action="store_true", default=False,
            help="also generate .discarded files.")
    option_parser.add_option("-f", "--filtered", dest="filtered",
            action="store_true", default=False,
            help="also generate .filtered files.")
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
    ntc = NERTrainingCallback(trie, options.discarded, options.filtered)
    ntc.read_gold(args[1])
    if options.redirects is not None:
        for redirect_file in options.redirects:
            ntc.read_redirects(redirect_file)
    if options.titles is not None:
        for titles_file in options.titles:
            ntc.read_titles(lt, titles_file)
    
    cr = ConllReader([ntc])
    for wiki_file in args[2:]:
        cr.read(wiki_file)

