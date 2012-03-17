from langtools.io.conll2.conll_reader import DefaultConllCallback, ConllReader
from langtools.utils.cascading_config import CascadingConfigParser

class DateTemplateCallback(DefaultConllCallback):
    def __init__(self, date_templates):
        self.date_templates = set(t.strip() for t in date_templates.decode('utf-8').split(','))

    def documentStart(self, title):
        DefaultConllCallback.documentStart(self, title)
    
    def templates(self, templates):
        DefaultConllCallback.templates(self, templates)

        if len(self.date_templates & set(templates)) > 0:
            print "{0}\t{1}".format(self.cc_title.encode('utf-8'), 0)

if __name__ == '__main__':
    from optparse import OptionParser

    option_parser = OptionParser()
    option_parser.add_option("-l", "--language", dest="language",
            help="the Wikipedia language code. Default is en.", default="en")
    options, args = option_parser.parse_args()

    if len(args) < 2:
        print('Extracts the date-related Wikipedia pages. Output is the same ' +
              'as that of the NER category extractor script , with 0 as the ' +
              'NER category.\n')
        print('Usage: {0} config_file input_files+')
        print('       config_file: the configuration file. Must contain a section' +
              ' called <language option>-wikimedia')
        import sys
        sys.exit(1)

    config_parser = CascadingConfigParser(args[0])
    config = dict(config_parser.items(options.language + '-wikimedia'))

    dtc = DateTemplateCallback(config['date-templates'])
    cr = ConllReader([dtc])
    for wiki_file in args[1:]:
        cr.read(wiki_file)

