"""Extracts the training sentences from the wikipedia pages. A sentence is
considered a training sentence, all links in it are leading to wikipedia pages
whose NE category is known."""

import sys
import os
import os.path
if sys.version_info[0] >= 3:
    from conll_reader3 import DefaultConllCallback, ConllReader
    from file_utils3 import *
else:
    from conll_reader import DefaultConllCallback, ConllReader
    from file_utils import *
import cmd_utils

# Functionality needed:
# - language selection (English is different from Hungarian)
# - from Nothman et al, 2008 (and our ideas, which they blantantly stole in
#   their paper :)):
#   .link inference (article title, redirects, words in links)
#   .capitalization (first words, dates, personal titles) - last two English only
#   .adjectival forms (nationalities) - English only
#   .lowercase links: drop / analyse incoming link capitalization
# We need:
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
        self.sentence.append(u'{0}\t{1}'.format(
                u"\t".join(attributes), self.ner_bi()))

#    def add_ner(self, ner_type, new=False):
#        was_ner = self.ner_type
#        self.ner_type = ner_type
#        self.bi = 'B' if new else 'I'

    def ner_bi(self):
        """Prints the ner type and also converts 0 to O."""
        return '{0}-{1}'.format(self.bi, self.ner_type) if self.ner_type != 0 else 'O'
    
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
        
class FirstSentenceCallback(DefaultConllCallback):
    """Prints the first sentence of each page to a file. For NER training."""
    def __init__(self, out_dir):
        """@param out_dir the directory the output files will be put."""
        if not ensure_dir(out_dir):
            raise ValueError
        DefaultConllCallback.__init__(self)
        self._out_dir = out_dir
    
    def fileStart(self, file_name):
        """Opens the output file."""
        DefaultConllCallback.fileStart(self, file_name)
        self._out = FileWriter(
            os.path.join(self._out_dir, os.path.basename(file_name))).open()
        
    def documentStart(self, title):
        DefaultConllCallback.documentStart(self, title)
        self._words = []
        
    def fieldStart(self, field):
        DefaultConllCallback.fieldStart(self, field)
        self._sentence = (field.lower() == 'body' and not self.cc_redirect)
        
    def word(self, attributes):
        if self._sentence:
            self._words.append(attributes)
        
    def sentenceEnd(self):
        if self._sentence == True:
            if len(self._words) > 0:
                self._out.write(u"{0}{1}\t{2}\n".format(ConllReader.META_HEAD,
                    ConllReader.PAGE_LABEL, self.cc_title))
                self._out.write(u"{0}{1}\t{2}\n".format(ConllReader.META_HEAD,
                    ConllReader.FIELD_LABEL, self.cc_field))
                for word in self._words:
                    self._out.write(u"\t".join(word) + "\n")
                self._out.write("\n")
            self._sentence = False
        
    def fileEnd(self):
        """Closes the output file."""
        DefaultConllCallback.fileEnd(self)
        self._out.close()
        self._out = None

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
    NO_LINK, IN_LINK = 0, 1
    months = set(['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November',
                  'December'])
    nnps = set(['NNP', 'NNPS'])
    
    def __init__(self, out_dir):
        """Initializes the callback. The training sentences are written to
        C{outs}.
        @param outs the output stream to write the data to."""
        if not ensure_dir(out_dir):
            raise ValueError
        DefaultConllCallback.__init__(self)
        self._sent = SentenceData()
        self._out_dir = out_dir
        self._title = []
        self._cat = None
        self._gold_map = {}
        
    def read_gold(self, gold_file):
        """Reads the gold file and fills the {page -> category} map from them.
        Old values are not deleted."""
        gold = FileReader(gold_file, 'utf-8').open()
        for line in gold:
            kv = line.strip().split("\t")
            if len(kv) == 2:
                self._gold_map[kv[0]] = kv[1]
        gold.close()
        # TODO: logging
        #print len(self._gold_map)

    # ConllCallback methods
    def fileStart(self, file_name):
        """Opens the output file."""
        DefaultConllCallback.fileStart(self, file_name)
        self._out = FileWriter(
            os.path.join(self._out_dir, os.path.basename(file_name))).open()
            
    def fieldStart(self, field):
        DefaultConllCallback.fieldStart(self, field.lower())
        if (self.cc_field == 'title'):
            self._title = []
            self._cat = self._gold_map.get(self.cc_title, None)
        else:
            self.first = True
            self.mode = NERTrainingCallback.NO_LINK
    
    def word(self, attributes):
        """Records the words in a C{SentenceData} object."""
        if not self.cc_redirect:
            if self.cc_field == 'title':
                self._title.append(attributes[4])
            elif self.cc_field == 'body':
                if len(attributes) >= 5:
                    if self.first:
                        self.first = False
                        if attributes[0].lower() == 'redirect':
                            self.cc_redirect = True
                            return
                    if attributes[1] == 'B-link':
                        self._sent.ner_type = self._gold_map.get(attributes[2], 0)
                        if self._sent.ner_type != 0:
                            self.mode = NERTrainingCallback.IN_LINK
                            self._sent.bi = 'B'
                            self._sent.links_found += 1
                        else:
                            self.mode = NERTrainingCallback.NO_LINK
                            self._sent.links_lost += 1
                    elif attributes[1] == 'I-link':
                        self._sent.bi = 'I'
                    else:
                        if self.mode == NERTrainingCallback.IN_LINK:
                            self.mode = NERTrainingCallback.NO_LINK
                            self._sent.ner_type = 0
                        if self.__is_NNP(attributes):
                            self._sent.links_lost += 1
                    
                    self._sent.append(attributes)
                else:
                    # TODO: logging
                    sys.stderr.write("Illegal word record [{0}] in page {1}\n".format(
                        u','.join(attributes).encode('utf-8'),
                        self.cc_title.encode('utf-8')))
    
    def __is_NNP(self, attributes):
        """Decides if word is NNP. Also, if a title-cased word occurs in the
        title as well, sets the ner type to the current page's type (if any)."""
        if not attributes[4].istitle():
            return False
        elif attributes[4] in NERTrainingCallback.months:
            return False
        # TODO: solve this: use two passes.
#        elif attributes[4] in self._title and self._cat is not None:
#            self._sent.ner_type = self._cat
            return False
        elif attributes[3] in NERTrainingCallback.nnps:
            return True
        elif len(self._sent.sentence) > 0:
            return True
        elif attributes[3].startswith('N') or attributes[3].startswith('J'):
            return True
        else:
            return False
    
    def sentenceEnd(self):
        """If the sentence contains links only to entities whose types are
        known, it is written to the output file."""
        if self._sent.links_found > 0 and self._sent.links_lost == 0:
            self._sent.write(self._out)
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

if __name__ == '__main__':
    try:
        params, args = cmd_utils.get_params(sys.argv[1:], 'g:o:', 'go', 1)
    except ValueError:
        print('Usage: {0} -o output_directory (-g gold_file)+ wiki_directories')
        sys.exit()
    
    ntc = NERTrainingCallback(params['o'][0])
    
    for gold in params['g']:
        ntc.read_gold(gold)
    
    cr = ConllReader([ntc])
    for wiki_dir in args:
        for wiki_file in filter(os.path.isfile,
                [os.path.join(wiki_dir, infile) for infile in os.listdir(wiki_dir)]):
            cr.read(wiki_file)

