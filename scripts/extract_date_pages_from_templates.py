"""Extracts the date pages from the .templates file. Should be faster than
from the content files."""

from langtools.utils.file_utils import FileReader
from langtools.utils.cascading_config import CascadingConfigParser
import sys
import re

class DateTemplateFinder(object):
    PAGE_PATTERN = re.compile("^%%#PAGE\s(.+)$")

    def __init__(self, date_templates):
        self.date_templates = set(t.strip() for t in date_templates.decode('utf-8').split(','))
        self.page = None

    def read(self, template_file):
        with FileReader(template_file).open() as infile:
            for line in infile:
                line = line.strip()
                m = DateTemplateFinder.PAGE_PATTERN.match(line)
                if m is not None:
                    self.page = m.group(1)
                elif self.page is not None:
                    if line.startswith("Template\t"):
                        template = line[9:]
                        if template in self.date_templates:
                            print "{0}\t{1}".format(self.page.encode('utf-8'), 0)
                            self.page = None
        sys.stderr.write("File {0} parsed.\n".format(template_file))
        sys.stderr.flush()
        sys.stdout.flush()

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

    dtc = DateTemplateFinder(config['date-templates'])
    for wiki_file in args[1:]:
        dtc.read(wiki_file)

