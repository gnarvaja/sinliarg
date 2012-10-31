#!/usr/bin/python
from lxml import etree
import sys

grammar_file = sys.argv[1]
xml_file = sys.argv[2]

relaxng = etree.RelaxNG(file=grammar_file)
result = relaxng.validate(etree.parse(xml_file))

if not result:
    print >> sys.stderr, relaxng.error_log
    sys.exit(1)
sys.exit(0)
