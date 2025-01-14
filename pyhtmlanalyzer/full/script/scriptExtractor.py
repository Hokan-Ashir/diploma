#!/usr/bin/env/ python
# -*- coding: utf-8 -*-
# solution for non-unicode symbols
# taken from: http://godovdm.blogspot.ru/2012/02/python-27-unicode.html
#from __future__ import unicode_literals
import logging
from multiprocessing import Queue
from collections import defaultdict
from copy import copy, deepcopy
import hashlib
from math import log
import re
import timeit
import libemu
from pyhtmlanalyzer import CLSID
from pyhtmlanalyzer.commonFunctions import jsVariableRegExp, configNames
from pyhtmlanalyzer.commonFunctions.commonConnectionUtils import commonConnectionUtils
from pyhtmlanalyzer.commonFunctions.commonFunctions import commonFunctions
from pyhtmlanalyzer.commonFunctions.modulesRegister import modulesRegister
from pyhtmlanalyzer.commonFunctions.multiprocessing.processProxy import processProxy
from pyhtmlanalyzer.databaseUtils.databaseConnector import databaseConnector
from pyhtmlanalyzer.full.commonAnalysisData import commonAnalysisData

__author__ = 'hokan'

class scriptExtractor(commonAnalysisData):
    __name__ = 'scriptExtractor'

    # TODO make constant, maybe in more common file
    _scriptHashingFunctionName = 'getScriptContentHashing'

    __configDict = None
    __uri = None
    __listOfScriptTagsText = None
    __currentlyAnalyzingScriptCode = None
    # list of hashes from previously analyzed page
    # fills and pass to analyzer from other function
    __listOfHashes = None
    # list of previous rows corresponding to script pieces of current page
    # fills and pass to analyzer from other function
    __listOfIds = None

    # this list contain string like "X:Y", where X is real source line in script, and Y is order number in parser list
    # this complication is for cases when site consists of created several very long lines of html-code
    __listOfScriptTagsTextSourcelines = None
    __listOfIncludedScriptFiles = None
    __listOfIncludedScriptFilesContent = None
    __commentsRegExp = None
    __quotedStringsRegExp = None
    __dictOfSymbolsProbability = None

    __listOfAnalyzeFunctions = []

    # constructor
    def __init__(self, configDict, xmldata = None, pageReady = None):
        commonAnalysisData.__init__(self, xmldata, pageReady)
        if configDict is not None:
            self.__configDict = configDict
        else:
            logger = logging.getLogger(self.__class__.__name__)
            logger.error("Invalid parameters")
            return

        result = commonFunctions.getModuleContent(configNames.configFileName, r'[^\n\s=,]+\s*:\s*[^\n\s=,]+',
                                                  'Extractors functions',
                                                  self.__class__.__name__)
        self.__listOfAnalyzeFunctions = [item.split(':')[0].replace(' ', '') for item in result]
    #
    ###################################################################################################################

    def getListOfHashes(self):
        return self.__listOfHashes

    def setListOfHashes(self, listOfHashes):
        self.__listOfHashes = listOfHashes
    #
    ###################################################################################################################

    # number of eval() function calls in pure js inline-code
    def getNumberOfEvalFunctionCalls(self):
        def callbackFunction(text, arguments):
            arguments += text.count('eval(')
            return arguments

        arguments = 0
        return self.analyzeFunction(callbackFunction, arguments, True, True)

    #def getTotalNumberOfEvalFunctionCalls(self):
    #    return sum(self.getNumberOfEvalFunctionCalls())

    def printNumberOfEvalFunctionCalls(self):
        logger = logging.getLogger(self.__class__.__name__)
        numberOfEvalFunctionCalls = self.getNumberOfEvalFunctionCalls()
        if numberOfEvalFunctionCalls == 0:
            logger.warning("\nNone eval() functions calls")
            return

        logger.info("\nTotal number of eval() calls: " + str(numberOfEvalFunctionCalls))
    #
    ###################################################################################################################

    # number of setTimeout(), setInterval() function calls
    def getNumberOfSetTimeoutIntervalCalls(self):
        try:
            listOfFunctions = self.__configDict['script.set.timeout.functions']
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of set timeout-like functions, can't perform analysis")
            return

        def callbackFunction(text, arguments):
            for i in xrange(len(listOfFunctions)):
                arguments[i] += text.count('%s(' % listOfFunctions[i])
            return arguments

        arguments = [0, 0]
        return self.analyzeFunction(callbackFunction, arguments, True, True)

    def getTotalNumberOfSetTimeoutIntervalCalls(self):
        return sum(self.getNumberOfSetTimeoutIntervalCalls())

    def printNumberOfSetTimeoutIntervalCalls(self):
        logger = logging.getLogger(self.__class__.__name__)
        listOfSetTimeoutIntervalCalls = self.getNumberOfSetTimeoutIntervalCalls()
        if sum(listOfSetTimeoutIntervalCalls) == 0:
            logger.warning("\nNone setTimeout() or setInterval() function calls")
            return

        logger.info("\nTotal number of setTimeout(), setInterval() calls: "
              + str(sum(listOfSetTimeoutIntervalCalls)))
        logger.info("Number of setTimeout() calls: " + str(listOfSetTimeoutIntervalCalls[0]))
        logger.info("Number of setInterval() calls: " + str(listOfSetTimeoutIntervalCalls[1]))
    #
    ###################################################################################################################

    # ratio between words and keywords (numberOfKeyWordsCharacters / totalNumberOfCharacters)
    # list of reserved words is taken
    # from https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Reserved_Words
    # function replace keywords from copies of text() node content
    # then calculates number of keyWordCharacters as (totalNumberOfCharacters - numberOfCharactersWithoutKeyWords)
    def getKeywordsToWordsRatio(self):
        try:
            commonListOfKeyWords = self.__configDict['script.keywords']
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone keywords list - can't perform analysis")
            return

        def callbackFunction(text, arguments):
            # totalLengthOfScriptContent
            try:
                if self.getEncoding() is None:
                    tempText = text
                else:
                    tempText = text.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempText = text.encode('utf-8')

            arguments[0] += len(str(tempText))
            for keyword in commonListOfKeyWords:
                tempText = commonFunctions.replaceUnquoted(tempText, keyword, "")
            # totalLengthOfScriptContentWithoutKeywords
            arguments[1] += len(tempText)
            return arguments

        totalLengthOfScriptContent = 0
        totalLengthOfScriptContentWithoutKeywords = 0
        arguments = [totalLengthOfScriptContent, totalLengthOfScriptContentWithoutKeywords]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)

        # division by zero exception
        if arguments[0] == 0:
            return float(0)

        return float(arguments[0] - arguments[1]) / arguments[0]

    def printKeywordsToWordsRatio(self):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nKeywords-to-words ratio is: " + str(self.getKeywordsToWordsRatio()))
    #
    ###################################################################################################################

    # TODO ask if it's necessary to remove leading and back whitespaces
    # number of long strings
    def getListOfLongStrings(self, stringLength = 40, separatorList = ['\n', ';']):
        separator = '|'.join(separatorList)
        def callbackFunction(text, arguments):
            try:
                if self.getEncoding() is None:
                    tempText = text
                else:
                    tempText = text.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempText = text.encode('utf-8')

            stringsList = re.split(separator, str(tempText))
            for string in stringsList:
                if len(string) > stringLength:
                    arguments.append(string)
            return arguments

        return self.analyzeFunction(callbackFunction, [], True, False)

    def getNumberOfLongStrings(self, stringLength = 40, separatorList = ['\n', ';']):
        return len(self.getListOfLongStrings(stringLength, separatorList))

    def printNumberOfLongStrings(self, stringLength = 40, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        listOfLongStrings = self.getListOfLongStrings(stringLength, separatorList)
        if len(listOfLongStrings) == 0:
            logger.warning("\nNone long strings")
            return

        logger.info("\nTotal number of long strings: " + str(len(listOfLongStrings)))
        logger.info("List of long strings:")
        for string in listOfLongStrings:
            logger.info("length: " + str(len(string)) + "\n\t" + str(string))
    #
    ###################################################################################################################

    # number of built-in functions
    # list is taken from: http://www.w3schools.com/jsref/jsref_obj_global.asp
    # another list presented here: http://www.tutorialspoint.com/javascript/javascript_builtin_functions.htm
    # a lot more functions, but are all these functions built-in?
    # TODO ask this ^
    def getNumberOfBuiltInFunctions(self):
        try:
            listOfBuiltInFunctions = self.__configDict["script.built.in.functions"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of built-in functions - can't perform analysis")
            return


        def callbackFunction(text, arguments):
            for function in listOfBuiltInFunctions:
                arguments[function] += text.count('%s(' % function)
            return arguments

        arguments = defaultdict(int)
        return self.analyzeFunction(callbackFunction, arguments, True, True)

    def getTotalNumberOfBuiltInFunctions(self):
        return sum(self.getNumberOfBuiltInFunctions().values())

    def printNumberOfBuiltInFunctions(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictNumberOfBuiltInFunctions = self.getNumberOfBuiltInFunctions()
        if dictNumberOfBuiltInFunctions == None or sum(dictNumberOfBuiltInFunctions.values()) == 0:
            logger.warning("\nNone built-in functions")
            return

        logger.info("\nTotal number of built-in functions: " + str(sum(dictNumberOfBuiltInFunctions.values())))
        logger.info("Number of built-in functions:")
        for key, value in dictNumberOfBuiltInFunctions.items():
            if value > 0:
                logger.info(str(key) + " : " + str(value))
    #
    ###################################################################################################################

    # script's whitespace percentage
    def getScriptWhitespacePercentage(self):
        def callbackFunction(text, arguments):
            try:
                if self.getEncoding() is None:
                    tempText = text
                else:
                    tempText = text.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempText = text.encode('utf-8')

            # totalScriptLength
            arguments[0] += len(str(tempText))
            # whitespaceLength
            arguments[1] += str(tempText).count(" ")
            return arguments

        totalScriptLength = 0
        whitespaceLength = 0
        arguments = [totalScriptLength, whitespaceLength]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)

        # division by zero exception
        if arguments[0] == 0:
            return float(0)

        return float(arguments[1]) / arguments[0]

    def printScriptWhitespacePercentage(self):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nScript whitespace percentage: " + str(self.getScriptWhitespacePercentage() * 100) + "%")
    #
    ###################################################################################################################

    # average script line length
    def getAverageScriptLength(self):
        def callbackFunction(text, arguments):
            arguments += len(text)
            return arguments

        totalScriptLineLength = 0
        numberOfScriptLines = len(self.__listOfScriptTagsText) + len(self.__listOfIncludedScriptFiles)
        totalScriptLineLength = self.analyzeFunction(callbackFunction, totalScriptLineLength, True, False)

        # division by zero exception
        if numberOfScriptLines == 0:
            return float(0)

        return float(totalScriptLineLength) / numberOfScriptLines

    def printAverageScriptLineLength(self):
        logger = logging.getLogger(self.__class__.__name__)
        averageScriptLineLength = self.getAverageScriptLength()
        if averageScriptLineLength == 0:
            logger.warning("\nNone script elements - average script length equals 0")
            return

        logger.info("\nAverage script length: " + str(averageScriptLineLength))
    #
    ###################################################################################################################

    # average length of the strings used in the script
    def getAverageLengthOfStringsUsedInScript(self, separatorList = ['\n', ';']):
        separator = '|'.join(separatorList)
        def callbackFunction(text, arguments):
            try:
                if self.getEncoding() is None:
                    tempText = text
                else:
                    tempText = text.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempText = text.encode('utf-8')

            stringsList = re.split(separator, str(tempText))
            # totalNumberOfLines
            arguments[0] += len(stringsList)
            for string in stringsList:
                # totalNumberOfCharactersInLines
                arguments[1] += len(string)
            return arguments

        totalNumberOfLines = 0
        totalNumberOfCharactersInLines = 0
        arguments = [totalNumberOfLines, totalNumberOfCharactersInLines]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)

        # division by zero exception
        if arguments[0] == 0:
            return float(0)

        return arguments[1] / arguments[0]

    def printAverageLengthOfStringsUsedInScript(self, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        averageLineLengthUsedInScript = self.getAverageLengthOfStringsUsedInScript(separatorList)
        if averageLineLengthUsedInScript == 0:
            logger.warning("\nNone script elements - average line length used in script equals 0")
            return

        logger.info("\nAverage script line length: " + str(averageLineLengthUsedInScript))
    #
    ###################################################################################################################

    # number of characters in script content
    def getNumberCharactersInScriptContent(self):
        def callbackFunction(text, arguments):
            arguments += len(text)
            return arguments

        numberOfCharactersInPage = 0
        return self.analyzeFunction(callbackFunction, numberOfCharactersInPage, False, False)

    def printNumberCharactersInScriptContent(self):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nNumber of characters in script: " + str(self.getNumberCharactersInScriptContent()))
    #
    ###################################################################################################################

    #  probability of the script to contain shellcode
    def getShellcodeExistenceProbability(self, stringLength = 40, separatorList = ['\n', ';']):
        listOfLongStrings = self.getListOfLongStrings(stringLength, separatorList)
        listOfQuotedStrings = []
        # get all quoted strings via regExp (see initialize method)
        for string in listOfLongStrings:
            listOfQuotedStrings += re.findall(self.__quotedStringsRegExp, string)

        numberOfQuotedStrings = len(listOfQuotedStrings)

        # no quoted string - no PURE shellcode
        if (numberOfQuotedStrings == 0):
            return float(0)

        numberOfShellcodedStrings = 0
        for item in listOfQuotedStrings:
            # method 1: get number of non-printable ASCII characters
            # see http://donsnotes.com/tech/charsets/ascii.html
            regEx = re.compile(r'[\x00-\x1f]+')
            numberOfShellcodedStrings += 1 if re.match(regEx, item) != None else 0

            # method 2: if the string is a consecutive block of characters in the ranges a-f, A-F, 0-9
            regEx = re.compile(r'"([%\\]?[ux][a-fA-f0-9]+)+"')
            numberOfShellcodedStrings += 1 if re.match(regEx, item) != None else 0

            # TODO maybe implement, difficult to get this via RegExp
            # method 3: if certain characters are repeated at regular intervals in the string

        return (float(numberOfShellcodedStrings) / numberOfQuotedStrings) * 100

    def printShellcodeExistenceProbability(self, stringLength = 40, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        percentageOfShellcodedQuotedStrings = self.getShellcodeExistenceProbability(stringLength, separatorList)
        logger.info("\nPercentage of shellcoded quoted strings: " + str(percentageOfShellcodedQuotedStrings) + "%")
    #
    ###################################################################################################################

    # probability of the script to contain shellcode (advanced version based on libemu library)
    # see http://nuald.blogspot.ru/2010/10/shellcode-detection-using-libemu.html

    def getShellcodeExistenceProbabilityAdvanced(self, stringLength = 40, separatorList = ['\n', ';']):
        listOfLongStrings = self.getListOfLongStrings(stringLength, separatorList)
        listOfQuotedStrings = []
        # get all quoted strings via regExp (see initialize method)
        for string in listOfLongStrings:
            listOfQuotedStrings += re.findall(self.__quotedStringsRegExp, string)

        numberOfQuotedStrings = len(listOfQuotedStrings)

        # no quoted strings - no PURE shellcode
        if numberOfQuotedStrings == 0:
            return float(0)

        numberOfShellcodedStrings = 0
        emulator = libemu.Emulator()
        for item in listOfQuotedStrings:
            numberOfShellcodedStrings += 1 if emulator.test(item) != None else 0

        # NOTE: this library cant recognize shellcode if it has "%u023423" format, that's why we first test strings manually
        # and then replace "%u" with "\\x" if nothing is found
        # Also this library cant recognize "long" characters as \x0099
        if numberOfShellcodedStrings == 0:
            for item in listOfQuotedStrings:
                numberOfShellcodedStrings += 1 if emulator.test(str(item).replace("%u", "\\x")) != None else 0

        return (float(numberOfShellcodedStrings) / numberOfQuotedStrings) * 100

    def printShellcodeExistenceProbabilityAdvanced(self, stringLength = 40, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        percentageOfShellcodedQuotedStrings = self.getShellcodeExistenceProbabilityAdvanced(stringLength, separatorList)
        logger.info("\nPercentage of shellcoded quoted strings: " + str(percentageOfShellcodedQuotedStrings) + "%")
    #
    ###################################################################################################################

    # the number of strings containing "iframe"
    def getNumberOfIFrameStrings(self, stringLength = -1, separatorList = ['\n', ';']):
        listOfStrings = self.getListOfLongStrings(stringLength, separatorList)
        listOfStringsWithIFrame = []
        for item in listOfStrings:
            if len(item) > len(commonFunctions.replaceUnquoted(item, '<iframe', '')):
                listOfStringsWithIFrame.append(item)
        return listOfStringsWithIFrame

    def getTotalNumberOfIFrameStrings(self, stringLength = -1, separatorList = ['\n', ';']):
        return len(self.getNumberOfIFrameStrings(stringLength, separatorList))

    def printNumberOfIFrameStrings(self, stringLength = -1, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        listOfStringsWithIFrame = self.getNumberOfIFrameStrings(stringLength, separatorList)
        if len(listOfStringsWithIFrame) == 0:
            logger.warning("\nNone strings with \'iframe\' tag")
            return

        logger.info("\nTotal number of strings with \'iframe\': " + str(len(listOfStringsWithIFrame)))
        logger.info("Number of strings with \'iframe\':")
        for item in listOfStringsWithIFrame:
            logger.info("length: " + str(len(item)) + "\n\t" + str(item))
    #
    ###################################################################################################################

    # number of suspicious strings
    def getNumberOfSuspiciousStrings(self, stringLength = -1, separatorList = ['\n', ';']):
        try:
            listOfSuspiciousTags = self.__configDict["script.suspicious.tags"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of suspicious tags, can't perform analysis")
            return

        listOfStrings = self.getListOfLongStrings(stringLength, separatorList)
        dictOfSuspiciousStrings = {}
        for item in listOfStrings:
            for item2 in listOfSuspiciousTags:
                if len(item) > len(commonFunctions.replaceUnquoted(item, '<' + item2, '')):
                    dictOfSuspiciousStrings[item2] = item
                    break
        return dictOfSuspiciousStrings

    def getTotalNumberOfSuspiciousStrings(self, stringLength = -1, separatorList = ['\n', ';']):
        return len(self.getNumberOfSuspiciousStrings(stringLength, separatorList))

    def printNumberOfSuspiciousStrings(self, stringLength = -1, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfSuspiciousStrings = self.getNumberOfSuspiciousStrings(stringLength, separatorList)
        if dictOfSuspiciousStrings == None or sum(dictOfSuspiciousStrings.values()) == 0:
            logger.warning("\nNone strings with suspicious tags")
            return

        logger.info("\nTotal number of strings with suspicious tags: " + str(sum(dictOfSuspiciousStrings.values())))
        logger.info("Number of strings with suspicious tags:")
        for key, value in dictOfSuspiciousStrings.items():
            logger.info("length: " + str(len(value)) + "\n<" + str(key) + ">:\n\t" + str(value))
    #
    ###################################################################################################################

    # maximum length of the script's strings
    def getMaximumLengthOfScriptStrings(self, separatorList = ['\n', ';']):
        separator = '|'.join(separatorList)
        def callbackFunction(text, arguments):
            try:
                if self.getEncoding() is None:
                    tempText = text
                else:
                    tempText = text.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempText = text.encode('utf-8')

            stringsList = re.split(separator, str(tempText))
            for string in stringsList:
                if len(string) > arguments:
                    arguments = len(string)
            return arguments

        maximumLengthOfScripts = 0
        return self.analyzeFunction(callbackFunction, maximumLengthOfScripts, True, False)

    def printMaximumLengthOfScriptStrings(self, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nMaximum length of script strings: " + str(self.getMaximumLengthOfScriptStrings(separatorList)))
    #
    ###################################################################################################################

    # number of suspicious objects used in the script
    def getObjectsWithSuspiciousContent(self):
        # suitable for content (like in 2575.html)
        def callbackFunction(text, arguments):
            for key in CLSID.clsidlist.keys():
                # here and after we upper case regexps, cause in initialization() method we made
                # all script content upper-cased
                regExp = re.compile(r'OBJECT.+CLASSID\s*=\s*[\'"]CLSID:%s' % key)
                numberOfKeyObjects = len(re.findall(regExp, text))
                if numberOfKeyObjects > 0:
                    arguments[key] += numberOfKeyObjects

            for key in CLSID.clsnamelist.keys():
                regExp = re.compile(r'OBJECT.+PROGID\s*=\s*[\'"]%s' % key)
                numberOfKeyObjects = len(re.findall(regExp, text))
                if numberOfKeyObjects > 0:
                    arguments[key] += numberOfKeyObjects
            return arguments

        dictOfSuspiciousObjects = defaultdict(int)

        return self.analyzeFunction(callbackFunction, dictOfSuspiciousObjects, True, False)

    def getTotalNumberOfObjectsWithSuspiciousContent(self):
        return sum(self.getObjectsWithSuspiciousContent().values())

    def printNumberOfObjectsWithSuspiciousContent(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfSuspiciousObjects = self.getObjectsWithSuspiciousContent()
        if sum(dictOfSuspiciousObjects.values()) == 0:
            logger.warning("\nNone suspicious objects")
            return

        logger.info("\nTotal number of suspicious objects: " + str(sum(dictOfSuspiciousObjects.values())))
        #sys.stdout.write("Number of suspicious objects:")
        logger.info("Number of suspicious objects:")
        for key, value in dictOfSuspiciousObjects.items():
            if value > 0:
                logger.info(str(key) + ": " + str(value))
    #
    ###################################################################################################################

    # number of long variable or function names used in the code
    def getNumberOfLongVariableOrFunction(self, variableNameLength = 20, functionNameLength = 20):
        # count only variable declarations; they can be only unique
        variableRegExp = re.compile(ur'var[\s\t]+%s{%d,}'
                                    % (jsVariableRegExp.jsVariableNameRegExp, variableNameLength))

        # count all functions;
        # NOTE: can be duplications
        # TODO ask (left or refactor?)
        # we can make set of found functions
        # but need to cut off ending '(' element and leading spaces, tabs, '=' and '.'
        functionRegExp = re.compile(ur'[\s\t=\.\n]+%s{%d,}[\s\t]*\('
                                    % (jsVariableRegExp.jsVariableNameRegExp, functionNameLength))
        def callbackFunction(text, arguments):
            try:
                if self.getEncoding() is None:
                    tempText = text
                else:
                    tempText = text.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempText = text.encode('utf-8')

            arguments[0] += len(re.findall(variableRegExp, tempText))
            arguments[1] += len(re.findall(functionRegExp, tempText))
            return arguments

        numberOfLongVariablesNames = 0
        numberOfLongFunctionsNames = 0
        arguments = [numberOfLongVariablesNames, numberOfLongFunctionsNames]
        return self.analyzeFunction(callbackFunction, arguments, True, False)

    def getTotalNumberOfLongVariableOrFunction(self, variableNameLength = 20, functionNameLength = 20):
        return sum(self.getNumberOfLongVariableOrFunction(variableNameLength, functionNameLength))

    def printNumberOfLongVariableOrFunction(self, variableNameLength = 20, functionNameLength = 20):
        logger = logging.getLogger(self.__class__.__name__)
        listOfLongVariableOfFunction = self.getNumberOfLongVariableOrFunction(variableNameLength, functionNameLength)
        if sum(listOfLongVariableOfFunction) == 0:
            if listOfLongVariableOfFunction[0] == 0:
                logger.warning("\nNone variable names longer than %d chars" % variableNameLength)
            if listOfLongVariableOfFunction[1] == 0:
                logger.warning("\nNone function names longer than %d chars" % functionNameLength)
            return

        logger.info("\nTotal number of variable names longer than %d chars and function names longer than %d chars: "
              % (variableNameLength, functionNameLength) + str(sum(listOfLongVariableOfFunction)))
        logger.info("Number of variable names longer than %d chars: " % variableNameLength + str(listOfLongVariableOfFunction[0]))
        logger.info("Number of function names longer than %d chars: " % functionNameLength + str(listOfLongVariableOfFunction[1]))
    #
    ###################################################################################################################

    # get whole script letter-entropy statistics
    def getWholeScriptEntropyStatistics(self):
        def callbackFunction(text, arguments):
            arguments[0] += len(text)
            for letter in text:
                arguments[1][letter] += 1
            return arguments

        # get probability statistics
        totalNumberOfLettersInScript = 0
        dictOfSymbolsProbability = defaultdict(float)
        arguments = [totalNumberOfLettersInScript, dictOfSymbolsProbability]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)

        for key, value in arguments[1].items():
            arguments[1][key] /= arguments[0]

        return arguments[1]
    #
    ###################################################################################################################

    # entropy of the script as a whole
    def getScriptWholeEntropy(self):
        def callbackFunction(text, arguments):
            for letter in text:
                if arguments[1][letter] <= 0:
                    continue

                arguments[0] += (arguments[1][letter] * log(arguments[1][letter], 2))
            return arguments

        # in case we're running getScriptEntropy for each script separately, we must recalculate entropy dictionary
        # for every script piece
        if (self.__dictOfSymbolsProbability is None or self.__currentlyAnalyzingScriptCode is not None):
            # in case we're calculating entropy for each piece of code
            # so dictionary must be removed and recreated
            if self.__dictOfSymbolsProbability is not None:
                del self.__dictOfSymbolsProbability

            self.__dictOfSymbolsProbability = self.getWholeScriptEntropyStatistics()

        # calculate entropy
        entropy = 0.0
        arguments = [entropy, self.__dictOfSymbolsProbability]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)
        arguments[0] *= -1
        return arguments[0]

    def printScriptWholeEntropy(self):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nWhole script entropy: " + str(self.getScriptWholeEntropy()))
    #
    ###################################################################################################################

    # entropy of the script nodes
    def getScriptNodesEntropy(self):
        dictOfEntropy = defaultdict(float)

        def callbackFunction(text, arguments, i, inlineTagContent):
            dictOfSymbolsProbability = defaultdict(float)
            totalNumberOfLettersInScript = len(text)
            # get probability statistics
            for letter in text:
                dictOfSymbolsProbability[letter] += 1

            for key, value in dictOfSymbolsProbability.items():
                dictOfSymbolsProbability[key] /= totalNumberOfLettersInScript

            # calculating entropy
            for letter in text:
                if dictOfSymbolsProbability[letter] <= 0:
                    continue

                if inlineTagContent:
                    arguments[self.__listOfScriptTagsTextSourcelines[i]] += (dictOfSymbolsProbability[letter] * log(dictOfSymbolsProbability[letter], 2))
                else:
                    arguments[self.__listOfIncludedScriptFiles[i]] += (dictOfSymbolsProbability[letter] * log(dictOfSymbolsProbability[letter], 2))

            if inlineTagContent:
                arguments[self.__listOfScriptTagsTextSourcelines[i]] *= -1
            else:
                arguments[self.__listOfIncludedScriptFiles[i]] *= -1

            return arguments

        for i in xrange(len(self.__listOfScriptTagsText)):
            # deleting comments
            text = re.sub(self.__commentsRegExp, '', self.__listOfScriptTagsText[i])
            dictOfEntropy = callbackFunction(text, dictOfEntropy, i, True)

        for i in xrange(len(self.__listOfIncludedScriptFilesContent)):
            # deleting comments
            scriptContent = re.sub(self.__commentsRegExp, '', self.__listOfIncludedScriptFilesContent[i])
            dictOfEntropy = callbackFunction(scriptContent, dictOfEntropy, i, False)

        return dictOfEntropy


    def printScriptNodesEntropy(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfEntropy = self.getScriptNodesEntropy()
        if sum(dictOfEntropy.values()) == 0:
            logger.warning("\nNone script nodes - can't calculate entropy of nodes")
            return

        logger.info("\nEntropy of nodes:")
        for key, value in dictOfEntropy.items():
            logger.info("source line: " + str(key) + "\nentropy: " + str(value))
    #
    ###################################################################################################################

    # maximum entropy of all the script's strings (as whole script)
    def getMaximumEntropyOfWholeScriptStrings(self, separatorList = ['\n', ';'], withStringWithMaxEntropy = False):
        separator = '|'.join(separatorList)
        def callbackFunction(text, arguments):
            entropy = 0.0
            listOfStrings = re.split(separator, text)
            for string in listOfStrings:
                for letter in string:
                    if arguments[2][letter] <= 0:
                        continue

                    entropy += (arguments[2][letter] * log(arguments[2][letter], 2))
                entropy *= -1
                if entropy > arguments[0]:
                    arguments[0] = entropy
                    arguments[1] = string
            return arguments

        # calculate entropy
        maximumEntropy = 0.0
        stringWithMaximumEntropy = ""

         # in case we're running getScriptEntropy for each script separately, we must recalculate entropy dictionary
        # for every script piece
        if (self.__dictOfSymbolsProbability is None or self.__currentlyAnalyzingScriptCode is not None):
            # in case we're calculating entropy for each piece of code
            # so dictionary must be removed and recreated
            if self.__dictOfSymbolsProbability is not None:
                del self.__dictOfSymbolsProbability

            self.__dictOfSymbolsProbability = self.getWholeScriptEntropyStatistics()

        arguments = [maximumEntropy, stringWithMaximumEntropy, self.__dictOfSymbolsProbability]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)

        if withStringWithMaxEntropy:
            return [arguments[0], arguments[1]]
        else:
            return arguments[0]

    def printMaximumEntropyOfWholeScriptStrings(self, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        listOfMaximumStringEntropy = self.getMaximumEntropyOfWholeScriptStrings(separatorList,
                                                                                withStringWithMaxEntropy=True)
        if listOfMaximumStringEntropy[0] == 0.0:
            logger.warning("\nNone script nodes - can't calculate string maximum entropy (whole script)")
            return

        logger.info("\nMaximum string entropy (whole script): " + str(listOfMaximumStringEntropy[0]))
        logger.info("of string: " + str(listOfMaximumStringEntropy[1]))
    #
    ###################################################################################################################

    # maximum entropy of all the script's strings (as script node)
    def getMaximumEntropyOfScriptStrings(self, separatorList = ['\n', ';']):
        dictOfTagsEntropy = {}
        separator = '|'.join(separatorList)

        def callbackFunction(text, arguments, i, inlineTagContent):
            dictOfSymbolsProbability = defaultdict(float)
            for letter in text:
                dictOfSymbolsProbability[letter] += 1
            for key, value in dictOfSymbolsProbability.items():
                dictOfSymbolsProbability[key] /= len(text)

            # calculate entropy
            maximumEntropy = 0.0
            stringWithMaximumEntropy = ""
            listOfStrings = re.split(separator, text)
            for string in listOfStrings:
                entropy = 0.0
                for letter in string:
                    if dictOfSymbolsProbability[letter] <= 0:
                        continue

                    entropy += (dictOfSymbolsProbability[letter] * log(dictOfSymbolsProbability[letter], 2))
                entropy *= -1
                if entropy > maximumEntropy:
                    maximumEntropy = entropy
                    stringWithMaximumEntropy = string

            if inlineTagContent:
                dictOfTagsEntropy[self.__listOfScriptTagsTextSourcelines[i]] = [maximumEntropy, stringWithMaximumEntropy]
            else:
                dictOfTagsEntropy[self.__listOfIncludedScriptFiles[i]] = [maximumEntropy, stringWithMaximumEntropy]

            return arguments

        for i in xrange(len(self.__listOfScriptTagsText)):
            # deleting comments
            text = re.sub(self.__commentsRegExp, '', self.__listOfScriptTagsText[i])
            dictOfTagsEntropy = callbackFunction(text, dictOfTagsEntropy, i, True)

        for i in xrange(len(self.__listOfIncludedScriptFilesContent)):
            # deleting comments
            scriptContent = re.sub(self.__commentsRegExp, '', self.__listOfIncludedScriptFilesContent[i])
            dictOfTagsEntropy = callbackFunction(scriptContent, dictOfTagsEntropy, i, False)

        return dictOfTagsEntropy

    def printMaximumEntropyOfScriptStrings(self, separatorList = ['\n', ';']):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfTagsEntropy = self.getMaximumEntropyOfScriptStrings(separatorList)
        if len(dictOfTagsEntropy) == 0:
            logger.warning("\nNone script nodes - can't calculate string maximum entropy (by nodes)")
            return

        logger.info("\nMaximum string entropy (by nodes)")
        for key, value in dictOfTagsEntropy.items():
            logger.info("source line: " + str(key))
            logger.info("maximum string entropy of this node: " + str(value[0]))
            try:
                if self.getEncoding() is None:
                    tempValue = value[1]
                else:
                    tempValue = value[1].encode(self.getEncoding())
            except Exception, error:
                logger.warning(error)
                tempValue = value[1].encode('utf-8')

            logger.info("of string: " + str(tempValue))
    #
    ###################################################################################################################

    # the entropy of the strings declared in the script (probability from all script)
    def getEntropyOfStringsDeclaredInScriptByWholeScript(self):
        def callbackFunction(text, arguments):
            listOfStrings = re.findall(self.__quotedStringsRegExp, text)
            for string in listOfStrings:
                entropy = 0.0
                for letter in string:
                    if arguments[1][letter] <= 0:
                        continue

                    entropy += (arguments[1][letter] * log(arguments[1][letter], 2))
                entropy *= -1
                arguments[0][string] = entropy
            return arguments

        if (self.__dictOfSymbolsProbability is None):
            self.__dictOfSymbolsProbability = self.getWholeScriptEntropyStatistics()

        dictOfStringsEntropy = {}
        arguments = [dictOfStringsEntropy, self.__dictOfSymbolsProbability]
        arguments = self.analyzeFunction(callbackFunction, arguments, True, False)
        return arguments[0]

    def printEntropyOfStringsDeclaredInScriptByWholeScript(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfStringsEntropy = self.getEntropyOfStringsDeclaredInScriptByWholeScript()
        if len(dictOfStringsEntropy) == 0:
            logger.warning("\nNone script nodes - can't calculate entropy of strings declared in script (by whole script)")
            return

        logger.info("\nEntropy of strings declared in script (by whole script)")
        for key, value in dictOfStringsEntropy.items():
            try:
                if self.getEncoding() is None:
                    tempKey = key
                else:
                    tempKey = key.encode(self.getEncoding())
            except Exception, error:
                logger.warning(error)
                tempKey = key.encode('utf-8')

            logger.info("string: " + str(tempKey) + "\nentropy: " + str(value))
    #
    ###################################################################################################################

    # the entropy of the strings declared in the script (probability from nodes)
    def getEntropyOfStringsDeclaredInScriptByNodes(self):
        dictOfStringsEntropy = {}

        def callbackFunction(text, arguments):
            dictOfSymbolsProbability = defaultdict(float)
            # calculate probability statistics
            for letter in text:
                dictOfSymbolsProbability[letter] += 1
            for key, value in dictOfSymbolsProbability.items():
                dictOfSymbolsProbability[key] /= len(text)

            # get all quoted strings via regExp
            listOfStrings = re.findall(self.__quotedStringsRegExp, text)
            for string in listOfStrings:
                entropy = 0.0
                for letter in string:
                    if dictOfSymbolsProbability[letter] <= 0:
                        continue

                    entropy += (dictOfSymbolsProbability[letter] * log(dictOfSymbolsProbability[letter], 2))
                entropy *= -1
                arguments[string] = entropy

            return arguments

        return self.analyzeFunction(callbackFunction, dictOfStringsEntropy, True, False)

    def printEntropyOfStringsDeclaredInScriptByNodes(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfStringsEntropy = self.getEntropyOfStringsDeclaredInScriptByNodes()
        if len(dictOfStringsEntropy) == 0:
            logger.warning("\nNone script nodes - can't calculate entropy of strings declared in script (by nodes)")
            return

        logger.info("\nEntropy of strings declared in script (by nodes)")
        for key, value in dictOfStringsEntropy.items():
            try:
                if self.getEncoding() is None:
                    tempKey = key
                else:
                    tempKey = key.encode(self.getEncoding())
            except Exception, error:
                logger.warning(error)
                tempKey = key.encode('utf-8')

            logger.info("string: " + str(tempKey) + "\nentropy: " + str(value))
    #
    ###################################################################################################################

    # script content hashing
    # NOTE: we remove comments by default
    def getScriptContentHashingAll(self, includeComments = False):
        dictOfScriptTagsHashed = {}
        def callbackFunction(text, arguments, i, inlineTagContent):
            try:
                if self.getEncoding() is None:
                    pageHashSHA256 = hashlib.sha256(text).hexdigest()
                    pageHashSHA512 = hashlib.sha512(text).hexdigest()
                else:
                    pageHashSHA256 = hashlib.sha256(text.encode(self.getEncoding())).hexdigest()
                    pageHashSHA512 = hashlib.sha512(text.encode(self.getEncoding())).hexdigest()
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                pageHashSHA256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
                pageHashSHA512 = hashlib.sha512(text.encode('utf-8')).hexdigest()

            if inlineTagContent:
                arguments[self.__listOfScriptTagsTextSourcelines[i]] = [pageHashSHA256, pageHashSHA512]
            else:
                arguments[self.__listOfIncludedScriptFiles[i]] = [pageHashSHA256, pageHashSHA512]

            return arguments

        for i in xrange(len(self.__listOfScriptTagsText)):
            text = copy(self.__listOfScriptTagsText[i])
            if not includeComments:
                # deleting comments
                text = re.sub(self.__commentsRegExp, '', self.__listOfScriptTagsText[i])
            dictOfScriptTagsHashed = callbackFunction(text, dictOfScriptTagsHashed, i, True)

        for i in xrange(len(self.__listOfIncludedScriptFilesContent)):
            scriptContent = copy(self.__listOfIncludedScriptFilesContent[i])
            if not includeComments:
                # deleting comments
                scriptContent = re.sub(self.__commentsRegExp, '', self.__listOfIncludedScriptFilesContent[i])
            dictOfScriptTagsHashed = callbackFunction(scriptContent, dictOfScriptTagsHashed, i, False)

        return dictOfScriptTagsHashed

    def getScriptContentHashing(self, includeComments = False):
        if self.__currentlyAnalyzingScriptCode >= len(self.__listOfScriptTagsText):
            text = copy(self.__listOfIncludedScriptFilesContent[self.__currentlyAnalyzingScriptCode - len(self
            .__listOfScriptTagsText)])
        else:
            text = copy(self.__listOfScriptTagsText[self.__currentlyAnalyzingScriptCode])

        if not includeComments:
            # deleting comments
            text = re.sub(self.__commentsRegExp, '', text)

        try:
            if self.getEncoding() is None:
                pageHashSHA256 = hashlib.sha256(text).hexdigest()
                pageHashSHA512 = hashlib.sha512(text).hexdigest()
            else:
                pageHashSHA256 = hashlib.sha256(text.encode(self.getEncoding())).hexdigest()
                pageHashSHA512 = hashlib.sha512(text.encode(self.getEncoding())).hexdigest()
        except Exception, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            pageHashSHA256 = hashlib.sha256(text.encode('utf-8')).hexdigest()
            pageHashSHA512 = hashlib.sha512(text.encode('utf-8')).hexdigest()

        return [pageHashSHA256, pageHashSHA512]

    def printScriptContentHashing(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfScriptTagsHashed = self.getScriptContentHashingAll()
        if len(dictOfScriptTagsHashed) == 0:
            logger.warning("\nNone script content to hash")
            return

        logger.info("\nScript content hashing")
        for key, value in dictOfScriptTagsHashed.items():
            logger.info("line: " + str(key) + "\n\tsha256: " + str(value[0]) + "\n\tsha512: " + str(value[1]))
    #
    ###################################################################################################################

    # number of event attachments
    def getNumberOfEventAttachments(self):
        try:
            listOfEvents = self.__configDict["script.events"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of events, can't perform analysis")
            return

        try:
            listOfAttachmentFunctionsEvents = self.__configDict["script.event.functions"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of event attachment functions, can't perform analysis")
            return

        def callbackFunction(text, arguments):
            for eventFunction in listOfAttachmentFunctionsEvents:
                for event in listOfEvents:
                    # addEventListener and initEvent get event _without_ 'on' characters at the beginning
                    if str(eventFunction).startswith("add") or str(eventFunction).startswith("init"):
                        # regexp, for both single & double quoted strings
                        regEx = re.compile(r'%s\s*\(\s*"%s"|%s\s*\(\s*\'%s\''
                                           % (eventFunction,
                                              str(event).lstrip("on"),
                                              eventFunction,
                                              str(event).lstrip("on")))
                    else:
                        regEx = re.compile(r'%s\s*\(\s*"%s"|%s\s*\(\s*\'%s\''
                                           % (eventFunction,
                                              event,
                                              eventFunction,
                                              event))
                    arguments[eventFunction][event] += len(re.findall(regEx, text))
            return arguments

        dictOfEventAttachments = {}
        for eventFunction in listOfAttachmentFunctionsEvents:
            dictOfEventAttachments[eventFunction] = {}
            for event in listOfEvents:
                dictOfEventAttachments[eventFunction][event] = 0
        return self.analyzeFunction(callbackFunction, dictOfEventAttachments, True, True)

    def printNumberOfEventAttachments(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfEventAttachments = self.getNumberOfEventAttachments()
        if dictOfEventAttachments == None:
            logger.warning("\nNone event attachments")
            return

        # split conditions due to slow speed of sum equation
        numberOfEventAttachments = 0
        for item in dictOfEventAttachments.values():
            numberOfEventAttachments += sum(dict(item).values())

        if numberOfEventAttachments == 0:
            logger.warning("\nNone event attachments")
            return

        logger.info("\nTotal number of event attachments: " + str(numberOfEventAttachments))
        logger.info("Number of event attachments:")
        for key, value in dictOfEventAttachments.items():
            logger.info(str(key) + ": ")
            for key2, value2 in value.items():
                logger.info("\t " + str(key2) + ": " + str(value2))
    #
    ###################################################################################################################

    # number of direct string assignments
    def getNumberOfDirectStringAssignments(self):
        # get all quoted strings via regExp (see initialize method)
        def callbackFunction(text, arguments):
            arguments += len(re.findall(self.__quotedStringsRegExp, text))
            return arguments

        numberOfDirectStringAssignments = 0
        return self.analyzeFunction(callbackFunction, numberOfDirectStringAssignments, True, False)

    def printNumberOfDirectStringAssignments(self):
        logger = logging.getLogger(self.__class__.__name__)
        numberOfDirectStringAssignments = self.getNumberOfDirectStringAssignments()
        if numberOfDirectStringAssignments == 0:
            logger.warning("\n None string assignments")
            return

        logger.info("\nTotal number of string assignments: " + str(numberOfDirectStringAssignments))
    #
    ###################################################################################################################

    # number of string modification functions
    def getNumberOfStringModificationFunctions(self):
        try:
            listOfStringModificationFunctions = self.__configDict["script.string.modification.functions"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of string modification functions, can't perform analysis")
            return

        def callbackFunction(text, arguments):
            for functionName in listOfStringModificationFunctions:
                regEx = re.compile(r'\.%s\s*\(\s*' % functionName)
                arguments[functionName] += len(re.findall(regEx, text))
            return arguments

        dictOfStringModificationFunctions = defaultdict(int)
        return self.analyzeFunction(callbackFunction, dictOfStringModificationFunctions, True, True)

    def printNumberOfStringModificationFunctions(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfStringModificationFunctions = self.getNumberOfStringModificationFunctions()
        if dictOfStringModificationFunctions == None or sum(dictOfStringModificationFunctions.values()) == 0:
            logger.warning("\nNone string modification functions")
            return

        logger.info("\nTotal number of string modification functions: " + str(sum(dictOfStringModificationFunctions.values())))
        for key, value in dictOfStringModificationFunctions.items():
            if value > 0:
                logger.info(str(key) + ": " + str(value))
    #
    ###################################################################################################################

    # number of built-in functions commonly used for deobfuscation
    def getNumberBuiltInDeobfuscationFunctions(self):
        try:
            listOfDeobfuscationFunctions = self.__configDict["script.deobfuscation.functions"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of deobfuscation functions, can't perform analysis")
            return

        def callbackFunction(text, arguments):
            for functionName in listOfDeobfuscationFunctions:
                regEx = re.compile(r'%s\s*\(\s*' % functionName)
                arguments[functionName] += len(re.findall(regEx, text))
            return arguments

        dictOfBuiltInDeobfuscationFunctions = defaultdict(int)
        return self.analyzeFunction(callbackFunction, dictOfBuiltInDeobfuscationFunctions, True, True)

    def printNumberBuiltInDeobfuscationFunctions(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfBuiltInDeobfuscationFunctions = self.getNumberBuiltInDeobfuscationFunctions()
        if dictOfBuiltInDeobfuscationFunctions == None or sum(dictOfBuiltInDeobfuscationFunctions.values()) == 0:
            logger.warning("\nNone deobfuscation functions")
            return

        logger.info("\nTotal number of deobfuscation functions: " + str(sum(dictOfBuiltInDeobfuscationFunctions.values())))
        for key, value in dictOfBuiltInDeobfuscationFunctions.items():
            if value > 0:
                logger.info(str(key) + ": " + str(value))
    #
    ###################################################################################################################

    # number of DOM modification functions
    def getNumberOfDOMModificationFunctions(self):
        try:
            listOfDOMModifyingMethods = self.__configDict["script.DOM.modifying.methods"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of DOM-modifying functions, can't perform analysis")
            return

        def callbackFunction(text, arguments):
            for method in listOfDOMModifyingMethods:
                regEx = re.compile(r'.%s\s*\(\s*' % method)
                arguments[method] += len(re.findall(regEx, text))
            return arguments

        dictOfDOMModyfingFunctions = defaultdict(int)
        return self.analyzeFunction(callbackFunction, dictOfDOMModyfingFunctions, True, True)

    def printNumberOfDOMModificationFunctions(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfDOMModyfingFunctions = self.getNumberOfDOMModificationFunctions()
        if dictOfDOMModyfingFunctions == None or sum(dictOfDOMModyfingFunctions.values()) == 0:
            logger.warning("\nNone DOM-modifying functions")
            return

        logger.info("\nTotal number of DOM-modifying functions: " + str(sum(dictOfDOMModyfingFunctions.values())))
        for key, value in dictOfDOMModyfingFunctions.items():
            if value > 0:
                logger.info(str(key) + ": " + str(value))
    #
    ###################################################################################################################

    # number of fingerprinting functions
    def getNumberOfFingerPrintingFunctions(self):
        try:
            listOfFingerprintingFunctions = self.__configDict["script.fingerprinting.functions"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of fingerprinting functions, can't perform analysis")
            return

        def callbackFunction(text, arguments):
            for function in listOfFingerprintingFunctions:
                arguments[function] += text.count(function)
            return arguments

        dictOfFingerprintingFunctions = defaultdict(int)
        return self.analyzeFunction(callbackFunction, dictOfFingerprintingFunctions, True, True)

    def printNumberOfFingerPrintingFunctions(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfFingerprintingFunctions = self.getNumberOfFingerPrintingFunctions()
        if dictOfFingerprintingFunctions == None or sum(dictOfFingerprintingFunctions.values()) == 0:
            logger.warning("\nNone fingerprinting functions")
            return

        logger.info("\nTotal number of fingerprinting functions: " + str(sum(dictOfFingerprintingFunctions.values())))
        for key, value in dictOfFingerprintingFunctions.items():
            if value > 0:
                logger.info(str(key) + ": " + str(value))
    #
    ###################################################################################################################

    # initialization
    def initialization(self, objectData, uri):
        self.setXMLData(objectData.getXMLData())
        self.setPageReady(objectData.getPageReady())
        self.setEncoding(objectData.getEncoding())
        self.__uri = uri
        listOfInlineScriptTags = self._xmldata.xpath('//script[not(@src)]')

        # we turn all text to upper register to speed up analysis in getObjectsWithSuspiciousContent() method
        # in which we can not to use re.I (case insensitive) flag
        self.__listOfScriptTagsText = []
        for item in listOfInlineScriptTags:
            if item.xpath('text()'):
                self.__listOfScriptTagsText.append(item.xpath('text()')[0])
        self.__listOfScriptTagsTextSourcelines = [str(item.sourceline) + ":" + str(listOfInlineScriptTags.index(item))
                                                  for item in listOfInlineScriptTags]

        # NOTE: we do not make dict of files of file content, cause it's too redundant; instead we use hashing
        # but here we get only unique files
        listOfFileScriptTags = self._xmldata.xpath('//script[@src]')
        self.__listOfIncludedScriptFiles = []
        self.__listOfIncludedScriptFilesContent = []
        for tag in listOfFileScriptTags:
            fileName = tag.xpath('@src')[0]
            if fileName not in self.__listOfIncludedScriptFiles:
                logger = logging.getLogger(self.__class__.__name__)
                logger.info(fileName)
                openedFile = commonConnectionUtils.openRelativeScriptObject(self.__uri, fileName)
                if openedFile is None or openedFile == []:
                    continue

                # we turn all text to upper register to speed up analysis in getObjectsWithSuspiciousContent() method
                # in which we can not to use re.I (case insensitive) flag
                self.__listOfIncludedScriptFilesContent.append(openedFile.getPageReady().upper())
                self.__listOfIncludedScriptFiles.append(fileName)

        # NOTE: only JS-comments
        # regexp for C/C++-like comments, also suitable for js-comments
        # ( /\* - begin C-like comment
        # [^\*/]* - everything except closing C-like comment 0+ times
        # \*/ - closing C-like comment
        # | - another part of regExp
        # // - begin of C++-like comment
        # .* - any symbol 0+ times
        # \n?) - until end of line, which can be off
        # (/\*[^\*/]*\*/|//.*\n?)
        #
        # advanced one @(/\*(.|[\r\n])*?\*/)|(//.*)@ taken from:
        # http://ostermiller.org/findcomment.html
        self.__commentsRegExp = re.compile(r'(/\*(.|[\r\n])*?\*/)|(//.*)')

        # get all quoted strings via regExp
        # (?:" - begin on quoted via "-symbol string and passive regExp group
        # [^"\n]* - any symbol 0+ times except closing quote symbol (") and \n
        # ["\n]) - end of quoted via "-symbol string, end-of-line can be also match end of quoted string
        # TODO maybe delete end-of-line from list of ending symbols ^ (also lower)
        # | - same part for string quoted via '-symbol (with escaping '-symbol)
        # (?:\'[^'\n]*[\'\n])
        # this double-part regexp needed in case when
        # one type of quotes appears in quoted string via other type of quotes
        self.__quotedStringsRegExp = re.compile(r'(?:"[^"\n]*["\n])|(?:\'[^\'\n]*[\'\n])')
    #
    ###################################################################################################################

    def analyzeFunction(self, callbackFunction, callbackArgument, removeComments = True, removeQuotedStrings = True):
        # in case we would like to analyze one, specific piece of script
        if self.__currentlyAnalyzingScriptCode != None:
            if self.__currentlyAnalyzingScriptCode > (len(self.__listOfScriptTagsText)
                                                        + len(self.__listOfIncludedScriptFiles)):
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning('Currently analyzing script code number (%s) is more than all script number in '
                               'page (%s)' % (self.__currentlyAnalyzingScriptCode, (len(self.__listOfScriptTagsText)
                                                        + len(self.__listOfIncludedScriptFiles))))
                return None

            #print(self.currentlyAnalyzingScriptCode)
            if self.__currentlyAnalyzingScriptCode >= len(self.__listOfScriptTagsText):
                text = self.__listOfIncludedScriptFilesContent[self.__currentlyAnalyzingScriptCode - len(self.__listOfScriptTagsText)]
            else:
                text = self.__listOfScriptTagsText[self.__currentlyAnalyzingScriptCode]

            if removeComments:
                # deleting comments
                text = re.sub(self.__commentsRegExp, '', text)

            if removeQuotedStrings:
                # remove all quoted strings via regExp
                text = re.sub(self.__quotedStringsRegExp, '', text)

            callbackArgument = callbackFunction(text, callbackArgument)
            return callbackArgument
        else:
            # in case we would like to analyze every script in page/file
            #begin = timeit.default_timer()
            for text in self.__listOfScriptTagsText:
                if removeComments:
                    # deleting comments
                    text = re.sub(self.__commentsRegExp, '', text)

                if removeQuotedStrings:
                    # remove all quoted strings via regExp
                    text = re.sub(self.__quotedStringsRegExp, '', text)

                callbackArgument = callbackFunction(text, callbackArgument)

            for scriptContent in self.__listOfIncludedScriptFilesContent:
                if removeComments:
                    # deleting comments
                    scriptContent = re.sub(self.__commentsRegExp, '', scriptContent)

                if removeQuotedStrings:
                    # remove all quoted strings via regExp
                    scriptContent = re.sub(self.__quotedStringsRegExp, '', scriptContent)

                # for future: in case callbackFunction can be list, so we check that before functions using
                # so as in inline js-code
                #if type(callbackFunctions) is list:
                #    callbackArgument = callbackFunctions[1](scriptContent, callbackArgument)
                #else:
                #    callbackArgument = callbackFunctions(scriptContent, callbackArgument)
                callbackArgument = callbackFunction(scriptContent, callbackArgument)

            #end = timeit.default_timer()
            #print("\nElapsed time: " + str(end - begin) + " seconds")

            return callbackArgument
    #
    ###################################################################################################################

    # public functions for outer packages
    # print result of all functions via reflection with default values
    # NOTE: no order in function calls
    def printAll(self, objectData, uri):
        logger = logging.getLogger(self.__class__.__name__)
        if objectData.getXMLData() is None \
            or objectData.getPageReady() is None:
                logger.error("Insufficient number of parameters")
                return
        self.initialization(objectData, uri)
        # TODO remove in production
        #if (True):
        #    return
        logger.info("\n\njs Analyser ----------------------")
        begin = timeit.default_timer()
        for funcName, funcValue in scriptExtractor.__dict__.items():
            if str(funcName).startswith("print") and callable(funcValue):
                try:
                    getattr(self, funcName)()
                except Exception, error:
                    logger = logging.getLogger(self.__class__.__name__)
                    logger.exception(error)
                    pass
        end = timeit.default_timer()
        logger.info("\nElapsed time: " + str(end - begin) + " seconds")
        logger.info("--------------------------------------")
    #
    ###################################################################################################################

    def getTotalAll(self, objectData, uri):
        logger = logging.getLogger(self.__class__.__name__)
        if objectData.getXMLData() is None \
            or objectData.getPageReady() is None:
                logger.error("Insufficient number of parameters")
                return
        self.initialization(objectData, uri)
        resultDict = {}
        for funcName, funcValue in scriptExtractor.__dict__.items():
            if str(funcName).startswith("getTotal") and callable(funcValue):
                try:
                    resultDict[funcName] = getattr(self, funcName)()
                except Exception, error:
                    logger = logging.getLogger(self.__class__.__name__)
                    logger.exception(error)
                    pass

        return [resultDict, scriptExtractor.__name__]
    #
    ###################################################################################################################

    def parallelViaScriptCodePieces(self, numberOfProcesses):
        totalNumberOfScriptCodes = len(self.__listOfScriptTagsText) + len(self.__listOfIncludedScriptFiles)
        # adapt function for script nodes - for every script piece of code make own process
        #if numberOfProcesses == 0:
        #    numberOfProcesses = len(self.listOfScriptTagsText) + len(self.listOfIncludedScriptFiles)

        # in case too much process number
        if numberOfProcesses > totalNumberOfScriptCodes:
            numberOfProcesses = totalNumberOfScriptCodes

        numberOfScriptCodePiecesByProcess = totalNumberOfScriptCodes / numberOfProcesses
        scriptCodesNotInProcesses = totalNumberOfScriptCodes % numberOfProcesses
        processQueue = Queue()
        proxyProcessesList = []
        resultList = []
        try:
            # start process for each function
            for i in xrange(0, numberOfScriptCodePiecesByProcess):
                for j in xrange(0, numberOfProcesses):
                    self.__currentlyAnalyzingScriptCode = i * numberOfProcesses + j
                    proxy = processProxy(None, [self, {'oneProcess' : True}, processQueue, 'analyzeAllFunctions'],
                                                commonFunctions.callFunctionByNameQeued)
                    proxyProcessesList.append(proxy)
                    proxy.start()

                # wait for process joining
                #for j in xrange(0, len(proxyProcessesList)):
                #    proxyProcessesList[j].join()

                # gather all data
                for j in xrange(0, len(proxyProcessesList)):
                    functionCallResult = processQueue.get()[1]
                    resultList.append(functionCallResult)

                del proxyProcessesList[:]
        except Exception, exception:
            print(exception)
            pass
        # if reminder(number of script codes, number of processes) != 0 - not all functions ran in separated processes
        # run other script codes in one, current, process
        if scriptCodesNotInProcesses != 0:
            for i in xrange(0, scriptCodesNotInProcesses):
                try:
                    self.__currentlyAnalyzingScriptCode = totalNumberOfScriptCodes - 1 - i

                    # here we can can calculate hashes per script code, cause it's "number" defined with row above
                    scriptPieceCodeHashes = getattr(self, self._scriptHashingFunctionName)()
                    if self.__listOfHashes is not None and scriptPieceCodeHashes in self.__listOfHashes:
                        resultList.append({configNames.id : self.__listOfIds[0]})
                        continue

                    functionCallResult = self.analyzeAllFunctions(oneProcess=True)
                    resultList.append(functionCallResult)
                except Exception, error:
                    logger = logging.getLogger(self.__class__.__name__)
                    logger.exception(error)
                    pass

        return resultList

    # analyze all list of analyze functions in one process
    def analyzeAllFunctions(self, oneProcess = False):
        # in case we analyze all functions of one script code piece in one separate process
        # designed to fulfill "parallelViaScriptCodePieces" method
        if oneProcess:
            resultDict = {}

            # here we already performing analysis on one piece of script code and can check need of analysis by
            # checking hash values <b> before </b> for-loop
            scriptPieceCodeHashes = getattr(self, self._scriptHashingFunctionName)()
            if self.__listOfHashes is not None and scriptPieceCodeHashes in self.__listOfHashes:
                # assuming listOfIds (previous analyzed script pieces in DB) and listOfHashes have same indices
                resultDict[configNames.id] = self.__listOfIds[self.__listOfHashes.index(scriptPieceCodeHashes)]
                return resultDict

            for funcName in self.__listOfAnalyzeFunctions:
                try:
                    functionCallResult = getattr(self, funcName)()
                    # if in result dict value = 0 - do not insert it
                    #if not ((type(functionCallResult) is int and functionCallResult == 0) or (type(
                    #        functionCallResult) is float and functionCallResult == 0.0)):
                    resultDict[funcName] = functionCallResult
                except Exception, error:
                    logger = logging.getLogger(self.__class__.__name__)
                    logger.exception(error)
                    continue

            # if we get here, so function calls above are correct and we can add hashes values to result dictionary
            # this values will be extract later
            resultDict['hashValues'] = [{'hash256' : scriptPieceCodeHashes[0],
                                         'hash512' : scriptPieceCodeHashes[1]}]

        # in case we analyze all script from whole page in one process
        else:
            resultDict = []
            resultInnerDict = {}
            for i in xrange(0, len(self.__listOfScriptTagsText) + len(self.__listOfIncludedScriptFiles)):
                self.__currentlyAnalyzingScriptCode = i

                # here we can can calculate hashes per script code, cause it's "number" defined with row above
                scriptPieceCodeHashes = getattr(self, self._scriptHashingFunctionName)()
                if self.__listOfHashes is not None and scriptPieceCodeHashes in self.__listOfHashes:
                    # assuming listOfIds (previous analyzed script pieces in DB) and listOfHashes have same indices
                    resultDict.append({configNames.id : self.__listOfIds[self.__listOfHashes.index(scriptPieceCodeHashes)]})
                    continue

                for funcName in self.__listOfAnalyzeFunctions:
                    try:
                        functionCallResult = getattr(self, funcName)()
                        # if in result dict value = 0 - do not insert it
                        #if not ((type(functionCallResult) is int and functionCallResult == 0) or (type(
                        #        functionCallResult) is float and functionCallResult == 0.0)):
                        resultInnerDict[funcName] = functionCallResult
                    except Exception, error:
                        logger = logging.getLogger(self.__class__.__name__)
                        logger.exception(error)
                        continue

                # if we get here, so function calls above are correct and we can add hashes values to result list
                # with analyzed data
                resultInnerDict['hashValues'] = [{'hash256' : scriptPieceCodeHashes[0],
                                                  'hash512' : scriptPieceCodeHashes[1]}]
                resultDict.append(deepcopy(resultInnerDict))
                for key in resultInnerDict.keys():
                    del resultInnerDict[key]

        return resultDict

    def getAllAnalyzeReport(self, **kwargs):
        try:
            kwargs['object']
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("Insufficient number of parameters")
            return [None, scriptExtractor.__name__]

        objectData = kwargs['object']
        if objectData.getXMLData() is None \
            or objectData.getPageReady() is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning('Error in input parameters:\n xmldata:\t%s\n pageReady:\t%s' % (objectData.getXMLData(),
                                                                                           objectData.getPageReady()))
            logger.warning("Insufficient number of parameters")
            return [None, scriptExtractor.__name__]

        objectData = commonConnectionUtils.openPage(kwargs['uri'])
        self.initialization(objectData, kwargs['uri'])

        # get previous hash values of script pieces, corresponding to this page
        listOfPreviousHashes = []
        connector = databaseConnector()
        register = modulesRegister()
        self.__listOfIds = []
        pageId = connector.select(register.getORMClass(configNames.page), [configNames.id], 'url', self.__uri)
        if pageId:
            previousHashValuesFks = connector.select(register.getORMClass(self.__class__.__name__),
                                                     ['pageFk'], 'pageFk', pageId[0].id)
            for fk in previousHashValuesFks:
                self.__listOfIds.append(fk.id)
                previousHashValues = connector.select(register.getORMClass('hashValues'), None, configNames.id, fk.id)
                if previousHashValues is not None \
                    and previousHashValues:
                    listOfPreviousHashes.append([previousHashValues[0].hash256, previousHashValues[0].hash512])

        if listOfPreviousHashes:
            self.__listOfHashes = copy(listOfPreviousHashes)

        numberOfProcesses = 1
        try:
            numberOfProcesses = kwargs['numberOfProcesses']
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            pass

        # in case too less processes
        if numberOfProcesses <= 0:
            numberOfProcesses = 1
        # in case too much process number
        elif numberOfProcesses > len(self.__listOfAnalyzeFunctions):
            numberOfProcesses = len(self.__listOfAnalyzeFunctions)

        # parallel by script codes - in limiting case one process per script piece
        if numberOfProcesses > 1:
            resultList = self.parallelViaScriptCodePieces(numberOfProcesses)
        else:
            resultList = self.analyzeAllFunctions()

        return [resultList, scriptExtractor.__name__]
    #
    ###################################################################################################################

    # TODO list
    # - the number of pieces of code resembling a deobfuscation routine
    # - AST structure comparing
    # - uri in more common class; or get uri & open file/page by js-Analyzer itself

    # TODO ask
    # is it possible to write redirection from folder where scripts lie to somewhere else?
    # I.e user loads page (in browser; then render it) & has access to scripts,
    # other way, analyzer open path-where-script-lie and sees nothing

    # TODO optimization (right now from 168 sec. to 5.5 sec.; from 1692 lines to 1166 lines)
    # - callback or anonymous functions in for-each loops calls in printXXXX methods
    # - merge regexps