import re

__author__ = 'hokan'

class commonFunctions:
    # replace 'old' value with 'new' value from text, WITHOUT replacing 'old' values in single or double quotes
    # taken from: http://bytes.com/topic/python/answers/38845-replace-string-except-inside-quotes
    # NOTE: thus replace commented strings
    @staticmethod
    def replaceUnquoted(text, old, new, quote = '"'):
        # suitable for one type of quotes
        #regExp = re.compile(r'%s([^\\%s]|\\[\\%s])*%s' % (quote, quote, quote, quote))
        quote1 = "'"
        # suitable for both types of quotes
        regExp = re.compile(r'(%s|%s)([^\\(%s|%s)]|\\[\\(%s|%s)])*(%s|%s)' % (quote, quote1,
                                                                              quote, quote1,
                                                                              quote, quote1,
                                                                              quote, quote1))

        out = ''
        last_pos = 0
        for m in regExp.finditer(text):
            out += text[last_pos:m.start()].replace(old, new)
            out += m.group()
            last_pos = m.end()

        return out + text[last_pos:].replace(old, new)