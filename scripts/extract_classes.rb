#!/usr/bin/ruby1.9

require "rexml/document"
require 'rexml/streamlistener'

# Parses owl xml ontologies, and extracts all classes (of type owl:Class)
# with their respective superclasses (rdfs:subClassOf property).
class OwlClassListener
  include REXML::StreamListener

  def initialize()
    @lines = ["owl#Thing: "]
    @class, @superclasses = nil, []
  end

  def tag_start(name, attrs)
    if name == "owl:Class"
      uri = attrs.fetch("rdf:about", nil)
      @class = strip_uri(uri) if uri
    elsif name == "rdfs:subClassOf"
      uri = attrs.fetch("rdf:resource", nil)
      @superclasses.push(strip_uri(uri)) if @class and uri
    end
  end
  def tag_end(name)
    if name == "owl:Class"
      @lines.push "#{@class}: #{@superclasses.join(",")}"
      @class, @superclasses = nil, []
    end
  end
  
  def strip_uri(uri)
    uri =~ /http:.*\/(.+)/ ? $1 : uri
  end
  
  def to_s
    puts @lines.sort.join("\n")
  end
end

# Parses the specified owl xml files, and extracts all classes with their
# respective superclasses.
# @param files a list of file names.
# @return a sorted list of <class name>: <superclass name>(,<superclass name>)*
#         lines
def extractClasses(files = [])
  list = OwlClassListener.new
  files.each do |file|
    xml = File.new(file)
    REXML::Document.parse_stream(xml, list)
  end
  puts list.to_s
end

if __FILE__ == $0
  extractClasses(ARGV)
end

