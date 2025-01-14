from collections import defaultdict
import hashlib
import logging
from multiprocessing import Queue
import operator
import timeit
import re
from pyhtmlanalyzer import CLSID
from pyhtmlanalyzer.commonFunctions import configNames
from pyhtmlanalyzer.commonFunctions.commonConnectionUtils import commonConnectionUtils
from pyhtmlanalyzer.commonFunctions.commonFunctions import commonFunctions
from pyhtmlanalyzer.commonFunctions.commonXPATHUtils import commonXPATHUtils
from pyhtmlanalyzer.commonFunctions.modulesRegister import modulesRegister
from pyhtmlanalyzer.commonFunctions.multiprocessing.processProxy import processProxy
from pyhtmlanalyzer.databaseUtils.databaseConnector import databaseConnector
from pyhtmlanalyzer.full.commonAnalysisData import commonAnalysisData
from pyhtmlanalyzer.full.commonURIAnalysisData import commonURIAnalysisData

__author__ = 'hokan'

class htmlExtractor(commonAnalysisData, commonURIAnalysisData):
    __name__ = 'htmlExtractor'

    # TODO make constant, maybe in more common file
    _scriptHashingFunctionName = 'getPageHashValues'

    __configDict = None
    __openedAsXML = None
    __listOfAnalyzeFunctions = []

    # list of hashes from previously analyzed page
    # fills and pass to analyzer from other function
    __listOfHashes = None

    # constructor
    def __init__(self, configDict, xmldata = None, pageReady = None, uri = None):
        commonAnalysisData.__init__(self, xmldata, pageReady)
        commonURIAnalysisData.__init__(self, uri)
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

    # elements with small area functions
    def getNumberOfElementsWithSmallArea(self, widthLimit, heightLimit, squarePixelsLimit):
        try:
            listOfTags = self.__configDict["html.elements.with.small.area"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of elements with small area, can't perform analysis")
            return

        dictOfElementsWithSmallArea = {}
        for item in listOfTags:
            dictOfElementsWithSmallArea[item] = len(self._xmldata.xpath(
            '//%s[@width <= %f or @height <= %f or (number(@width) * number(@height)) <= %f]'
            % (item, widthLimit, heightLimit, squarePixelsLimit)))
        return dictOfElementsWithSmallArea


    def getTotalNumberOfElementsWithSmallArea(self, widthLimit = 2.0, heightLimit = 2.0, squarePixelsLimit = 30.0):
        return sum(self.getNumberOfElementsWithSmallArea(widthLimit, heightLimit, squarePixelsLimit).values())


    def getTotalNumberOfElementsWithSmallAreaByDict(self, dictOfNumberOfElements):
        return sum(dictOfNumberOfElements.values())

    def printNumberOfElementsWithSmallArea(self, widthLimit = 2.0, heightLimit = 2.0, squarePixelsLimit = 30.0):
        numberOfElementsWithSmallAreaDict = self.getNumberOfElementsWithSmallArea(widthLimit, heightLimit, squarePixelsLimit)
        logger = logging.getLogger(self.__class__.__name__)
        if numberOfElementsWithSmallAreaDict == None or sum(numberOfElementsWithSmallAreaDict.values()) == 0:
            logger.warning("\nNone elements with small area (width less than %f, height less than %f, square less than %f"
                  % (widthLimit, heightLimit, squarePixelsLimit))
            return

        logger.info("\nTotal number of elements with small area (width less than %f, height less than %f, square less "
                "than %f: "
              % (widthLimit, heightLimit, squarePixelsLimit) + str(sum(numberOfElementsWithSmallAreaDict.values())))
        logger.info("Number of elements with small area (width less than %f, height less than %f, square less than %f:"
              % (widthLimit, heightLimit, squarePixelsLimit))
        for key, value in numberOfElementsWithSmallAreaDict.items():
            if value > 0:
                logger.info("<" + str(key) + ">: " + str(value))
    #
    ###################################################################################################################

    # duplicated elements functions
    def getNumberOfDuplicatedElements(self):
        # TODO cause xPath sees out-of-root html-tag tags as children of another html-tag, manage this; or left assuming
        # suspicious page
        try:
            listOfDuplicatedTags = self.__configDict["html.non.dulpicated.elemets"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of non-duplicated elements, can't perform analysis")
            return

        dictOfDuplicatedElementsCount = {}
        for item in listOfDuplicatedTags:
            dictOfDuplicatedElementsCount[item] = self._xmldata.xpath('count(//%s)' % item)
        return dictOfDuplicatedElementsCount


    def getTotalNumberOfDuplicatedElements(self):
        return sum(self.getNumberOfDuplicatedElements().values())


    def isElementsDuplicated(self):
        return True if self.getTotalNumberOfDuplicatedElements() > 4 else False

    def printNumberOfDuplicatedElements(self):
        logger = logging.getLogger(self.__class__.__name__)
        duplicatedElementsDict = self.getNumberOfDuplicatedElements()
        if duplicatedElementsDict == None or sum(duplicatedElementsDict.values()) == 0:
            logger.warning("\nNone duplicated elements")
            return

        logger.info("\nTotal number of core html elements: " + str(sum(duplicatedElementsDict.values())))
        logger.info("Number of core html elements:")
        for key, value in duplicatedElementsDict.items():
            if value > 0:
                logger.info("<" + str(key) + ">: " + str(value))
    #
    ###################################################################################################################

    # elements with suspicious content functions
    #//*[not(self::script or self::style)]/text()[string-length()
    def getNumberOfElementsWithSuspiciousContent(self, characterLength, whitespacePercentage):
        # first count length of content,
        # then check string with whitespaces has %whitespacePercentage% spaces;
        # furthermore we do not add strings without spaces at all ("and .." part of condition)
        tooLongCharacterStringsCount = self._xmldata.xpath('count(//text()[string-length() > %d])' % characterLength)
        tooLessWhitespacesStringsCount = self._xmldata.xpath(
            'count(//text()[(1 - (string-length(translate(., \' \', \'\')) div string-length())) < %f '
            'and (string-length(translate(., \' \', \'\')) != string-length())])'
            % whitespacePercentage)
        return [tooLongCharacterStringsCount, tooLessWhitespacesStringsCount]


    def getTotalNumberOfElementsWithSuspiciousContent(self, characterLength = 128, whitespacePercentage = 5.0):
        return sum(self.getNumberOfElementsWithSuspiciousContent(characterLength, whitespacePercentage))


    def getTotalNumberOfElementsWithSuspiciousContentByList(self, listOfNumberOfElements):
        return sum(listOfNumberOfElements)

    def printNumberOfElementsWithSuspiciousContent(self, characterLength = 128, whitespacePercentage = 5.0):
        logger = logging.getLogger(self.__class__.__name__)
        suspiciousElements = self.getNumberOfElementsWithSuspiciousContent(characterLength, whitespacePercentage)
        if sum(suspiciousElements) == 0:
            logger.warning("\nNone elements with suspicious content")
            return

        logger.info("\nNumber of suspicious elements:")
        logger.info("with length more than %d: " % characterLength + str(suspiciousElements[0]))
        logger.info("with less than %f percent of whitespaces: " % whitespacePercentage + str(suspiciousElements[1]))
    #
    ###################################################################################################################

    # it's impossible to get content of non-closing tag via lxml
    # but we can get content of void-tags parsing file in XML format and get @.tail@ node field instead of @text@
    # number of void-elements with content
    def getNumberOfVoidElementsWithContent(self):
        logger = logging.getLogger(self.__class__.__name__)
        if self.__openedAsXML == False:
            logger.error("\nObject not opened as XML, impossible to count of void elements with content")
            return

        try:
            listOfVoidTagNames = self.__configDict["html.void.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of void tags, can't perform analysis")
            return

        dictOfVoidElementsWithContent = defaultdict(int)
        for tag in listOfVoidTagNames:
            listOfTags = self._xmldata.xpath('//%s' % tag)
            for item in listOfTags:
                if item.tail != None and len(item.tail) > 0:
                    dictOfVoidElementsWithContent[tag] += 1
                    #self.xmldata.xpath('count(//%s[string-length(text()) > 0])' % tag)

        return dictOfVoidElementsWithContent

    def getTotalNumberOfVoidElementsWithContent(self):
        return sum(self.getNumberOfVoidElementsWithContent().values())

    def printNumberOfVoidElementsWithContent(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfVoidElementsWithContent = self.getNumberOfVoidElementsWithContent()
        if dictOfVoidElementsWithContent == None or sum(dictOfVoidElementsWithContent.values()) == 0:
            logger.warning("\nNone void elements with content")
            return

        logger.info("\nTotal number of void elements with content: " + str(sum(dictOfVoidElementsWithContent.values())))
        logger.info("Number of void elements with content:")
        for key, value in dictOfVoidElementsWithContent.items():
            if value > 0:
                logger.info("<" + str(key) + ">: " + str(value))
    #
    ###################################################################################################################

    # objects with suspicious content
    def getObjectsWithSuspiciousContent(self):
        dictOfSuspiciousObjects = {}
        for key in CLSID.clsidlist.keys():
            # we use value-of-classid-attribute.upper() cause we unsure that authors of malicious pages will
            # follow the rules
            itemsCount = self._xmldata.xpath('count(//object[%s = \'CLSID:%s\'])'
                                            % (commonXPATHUtils.toUpperCase('@classid', False), key))
            if itemsCount > 0:
                dictOfSuspiciousObjects[key] = itemsCount

        for key in CLSID.clsnamelist.keys():
            # here we use key.upper() cause not all CLSNames in upper case
            # we also use value-of-progid-attribute.upper() cause we unsure that authors of malicious pages will
            # follow the rules
            itemsCount = self._xmldata.xpath("count(//object[%s = '%s'])"
                                            % (commonXPATHUtils.toUpperCase('@progid', False), str(key).upper()))
            if itemsCount > 0:
                dictOfSuspiciousObjects[key] = itemsCount

        return dictOfSuspiciousObjects

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

    # number of included URLs
    def getIncludedURLs(self):
        try:
            listOfTags = self.__configDict["html.included.urls.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of tags with included URLs, can't perform analysis")
            return

        dictOfIncludedURLsOjects = {}
        for item in listOfTags:
            dictOfIncludedURLsOjects[item] = self._xmldata.xpath('count(//%s[@src])' % item)

        return dictOfIncludedURLsOjects

    def getTotalNumberOfIncludedURLs(self):
        return sum(self.getIncludedURLs().values())

    def printNumberOfIncludedURLs(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictElementsWithIncludedURLs = self.getIncludedURLs()
        if dictElementsWithIncludedURLs == None or sum(dictElementsWithIncludedURLs.values()) == 0:
            logger.warning("\nNone elements with included URLs")
            return

        logger.info("\nTotal number of elements with included URLs: " + str(sum(dictElementsWithIncludedURLs.values())))
        logger.info("Number of elements with included URLs:")
        for key, value in dictElementsWithIncludedURLs.items():
            if value > 0:
                logger.info("<" + str(key) + ">: " + str(value))
    #
    ###################################################################################################################

    # number of known malicious patterns
    def getNumberOfKnownMaliciousPatternObjects(self):
        # TODO add additional patterns
        listOfMaliciousPatterns = ['metaTagRedirection']
        dictOfMaliciousPatternObjects = {}
        for item in listOfMaliciousPatterns:
            if item == 'metaTagRedirection':
                # the presence of a meta tag that causes the refresh of the
                # page, pointing it to index.php?spl=, as this is very common in
                # pages redirecting to exploit servers.
                # also includes https:// case
                dictOfMaliciousPatternObjects[item]\
                    = self._xmldata.xpath('count(//meta[contains(%s, URL)'
                                         ' and (contains(%s, \'http://index.php?spl=\')'
                                         ' or contains(%s, \'https://index.php?spl=\'))])'
                                         % (commonXPATHUtils.toUpperCase('@content', False),
                                            commonXPATHUtils.toLowerCase('@content', False),
                                            commonXPATHUtils.toLowerCase('@content', False)))
        return dictOfMaliciousPatternObjects

    def getTotalNumberOfKnownMaliciousPatternObjects(self):
        return sum(self.getNumberOfKnownMaliciousPatternObjects().values())

    def printNumberOfKnownMaliciousPatternObjects(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictElementsWithMaliciousPatterns = self.getNumberOfKnownMaliciousPatternObjects()
        if sum(dictElementsWithMaliciousPatterns.values()) == 0:
            logger.warning("\nNone elements with malicious patterns")
            return

        logger.info("\nTotal number of elements with malicious patterns:"
              + str(sum(dictElementsWithMaliciousPatterns.values())))
        logger.info("Number of elements with malicious patterns:")
        for key, value in dictElementsWithMaliciousPatterns.items():
            if value > 0:
                logger.info("pattern: " + str(key) + " - " + str(value))
    #
    ###################################################################################################################

    # number of out-of-place tags
    def getNumberOutOfPlaceTags(self):
        # NOTE for future work there is more common list of restrictions for <head> tag:
        # http://www.w3schools.com/tags/tag_head.asp link
        # I've deleted <embed> and <script> tags cause they can be under <head> tag
        try:
            listOfUnderHeadTags = self.__configDict["html.under.head.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of under-head-tag elements, can't perform analysis")
            return

        try:
            listOfOutOfRootTags = self.__configDict["html.out.of.root.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of out-of-root-tag elements, can't perform analysis")
            return

        try:
            listOfBlockLevelTags = self.__configDict["html.block.level.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of block level elements, can't perform analysis")
            return

        try:
            listOfNonBlockTags = self.__configDict["html.non.block.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of non block level elements, can't perform analysis")
            return

        try:
            listOfBlockContentInlineTags = self.__configDict["html.no.block.content.inline.elements"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of no-block-content inline elements, can't perform analysis")
            return

        # result dictionary initialization
        # we don't use defaultdict() because of total statistics and opportunity getting KeyError exceptions
        dictElementsOutOfPlace = {}
        for item in listOfUnderHeadTags:
            dictElementsOutOfPlace[item] = 0
        for item in listOfOutOfRootTags:
            dictElementsOutOfPlace[item] = 0
        for item in listOfBlockLevelTags:
            dictElementsOutOfPlace[item] = 0
        for item in listOfNonBlockTags:
            dictElementsOutOfPlace[item] = 0
        for item in listOfBlockContentInlineTags:
            dictElementsOutOfPlace[item] = 0

        listOfUnderRootElements = self._xmldata.xpath('/*')[0].xpath('./*')
        for item in listOfUnderRootElements:
            # count number of tags outside root html-tag or in head or title
            if item.xpath('name(.)') == 'head':
                # cause <title> is child of <head> we removed it from comparison above
                for tag in listOfUnderHeadTags:
                    dictElementsOutOfPlace[tag] += item.xpath('count(.//%s)' % tag)
            elif item.xpath('name(.)') == 'html':
                # cause lxml sees out-of-root tag elements as children of another <html> tag,
                # in comparison above it mentioned
                # it is NOT root-html tag!
                for tag in listOfOutOfRootTags:
                    dictElementsOutOfPlace[tag] += item.xpath('count(.//%s)' % tag)

        # NOTE: deprecated tags like 'frame'-tag duplicated by 'p' tags
        # i.e. in VLC.htm tag <frame> in <html> will be empty text field (source line 65)
        # furthermore tag <p> presents at source line 65 with filled text field
        # count number of tags directly in root html-tag
        for item in listOfUnderRootElements:
            # if-statement faster then catch KeyError exception
            if item.tag in dictElementsOutOfPlace.keys():
                dictElementsOutOfPlace[item.tag] += 1

        # http://www.w3.org/TR/html401/sgml/dtd.html
        # http://www.w3.org/TR/html401/struct/text.html#edef-P
        # https://developer.mozilla.org/en-US/docs/HTML/Block-level_elements
        # https://developer.mozilla.org/en-US/docs/HTML/Inline_elements
        # http://dev.w3.org/html5/markup/syntax.html#void-element
        # count number of all block elements in block elements
        for tag in listOfNonBlockTags:
            # get all elements of type 'tag' from body (cause we already count out-of-body-tag elements)
            listOfTagElements = self._xmldata.xpath('/html/body//%s' % tag)
            for element in listOfTagElements:
                for tag2 in listOfBlockLevelTags:
                    # check that parent of this tag has name from list of block-type tags
                    if element.xpath('name(..) = \'%s\'' % tag2):
                        dictElementsOutOfPlace[tag2] += 1
                        break

        # check number of special inline elements with block content
        for tag in listOfBlockContentInlineTags:
            # get all elements of type 'tag' from body (cause we already count out-of-body-tag elements)
            listOfTagElements = self._xmldata.xpath('/html/body//%s' % tag)
            for element in listOfTagElements:
                # check that their parent has no text content
                if (element.xpath('..')[0].text == '\n' or element.xpath('..')[0].text == None):
                    # check if this tags have block content children
                    for tag2 in listOfBlockLevelTags:
                        if (element.xpath('count(.//%s)' % tag2) != 0):
                            dictElementsOutOfPlace[tag] += 1
                            break

        # check out existence of <title> tag in <head> tag or its duplication
        # this rule is taken from: http://www.w3schools.com/tags/tag_head.asp
        # and http://www.w3schools.com/tags/tag_title.asp
        # count <title> tags in valid <head> (under root <html>)
        # here we can make fast check of duplication of <title> tag like this:
        # if len(titleTagList) > 1:
        #    # more than one <title> tag - wrong
        #    dictElementsOutOfPlace['title'] += len(titleTagList) - 1
        #
        # but EVERY <title> tag may be misplaced, so we count <title> tags in valid <head>
        numberOfTitleTagsUnderValidHead = self._xmldata.xpath('count(/html/head//title)')
        if numberOfTitleTagsUnderValidHead >= 1:
            # here is at least one in-place <title>
            # subtract from all invalid <title> tags one valid
            dictElementsOutOfPlace['title'] = self._xmldata.xpath('count(//title)') - 1
        else:
            # otherwise all <title> tags are invalid
            dictElementsOutOfPlace['title'] = self._xmldata.xpath('count(//title)')

        return dictElementsOutOfPlace

    def getTotalNumberOutOfPlaceTags(self):
        return sum(self.getNumberOutOfPlaceTags().values())

    def printNumberOutOfPlaceTags(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOutOfPlaceTags = self.getNumberOutOfPlaceTags()
        if dictOutOfPlaceTags == None or sum(dictOutOfPlaceTags.values()) == 0:
            logger.warning("\nNone out of place elements")
            return

        logger.info("\nTotal number of elements out of place: " + str(sum(dictOutOfPlaceTags.values())))
        logger.info("Number of elements out of place:")
        for key, value in dictOutOfPlaceTags.items():
            if value > 0:
                logger.info("<" + str(key) + ">: " + str(value))
    #
    ###################################################################################################################

    # pages comparing via recursively subtrees comparing
    # NOTE: this function just compare subtrees by level of depth
    # so pages like:
    # <tag1>
    #   <tag2>
    #       <tag3>
    #          <sub_tree> ... </subtree>
    #       </tag3>
    #   </tag2>
    # <tag1>
    #
    # <tag1>
    #   <tag2>
    #       <tag4>
    #           <subtree> ... </subtree>
    #       </tag4>
    #   </tag2>
    # </tag1>
    #
    # will be different, even if subtrees are equal
    @staticmethod
    def getPagesPercentageMismatch(xmldataFirstPage, xmldataSecondPage):
        logger = logging.getLogger("getPagesPercentageMismatch")
        probablyNotMatch = (xmldataFirstPage.xpath('count(//*)') != xmldataSecondPage.xpath('count(//*)'))
        if probablyNotMatch:
            logger.info("\nThis pages probably not match")
        numberOfMismatchedTags = htmlExtractor.getNumberOfMismatchedTagNames(xmldataFirstPage.xpath('/*')[0],
                                                                            xmldataSecondPage.xpath('/*')[0])
        return numberOfMismatchedTags / xmldataFirstPage.xpath('count(//*)')

    @staticmethod
    def getNumberOfMismatchedTagNames(nodeFirstPage, nodeSecondPage):
        numberOfDifferentNodes = 0
        listChildElementsFirstPage = nodeFirstPage.xpath('./*')
        listChildElementsSecondPage = nodeSecondPage.xpath('./*')

        # TODO ask if this is necessary; sure it does
        # create pair lists that will be sorted by tag-name
        listPairChildFirstPage = []
        for item in listChildElementsFirstPage:
            listPairChildFirstPage.append((item.xpath('name(.)'), item))
        listPairChildFirstPage.sort(key=operator.itemgetter(0))

        listPairChildSecondPage = []
        for item in listChildElementsSecondPage:
            listPairChildSecondPage.append((item.xpath('name(.)'), item))
        listPairChildSecondPage.sort(key=operator.itemgetter(0))

        # always comparing fist element from first page child list, no index needed
        while True:
            if listPairChildFirstPage == []:
                break

            # get first element from first tag-list, search for its name in second list
            nodeNameFirstPage = listPairChildFirstPage[0][0]
            nodeNameSecondPage = None
            secondPageListIndex = -1
            for j in range(0, len(listPairChildSecondPage)):
                nodeNameSecondPage = listPairChildSecondPage[j][0]
                if nodeNameSecondPage == nodeNameFirstPage:
                    secondPageListIndex = j
                    break

            # can't find this tag, get number of all tags in subtree
            if nodeNameSecondPage is None:
                # get number of all childes ANY depth plus this tag name mismatch
                numberOfDifferentNodes += listPairChildFirstPage[0][1].xpath('count(.//*)') + 1
            # find one, recursively search other mismatches and delete match tag in second list
            else:
                # TODO here can be add attributes lists comparing
                numberOfDifferentNodes += \
                    htmlExtractor.getNumberOfMismatchedTagNames(listPairChildFirstPage[0][1],
                                                               listPairChildSecondPage[secondPageListIndex][1])
                listPairChildSecondPage.pop(secondPageListIndex)

            # delete first node
            listPairChildFirstPage.pop(0)

        # in case lists have different length (first page has less tags than second)
        # get number of all childes ANY depth plus this tag name mismatch
        for item in listPairChildSecondPage:
            numberOfDifferentNodes += item[1].xpath('count(.//*)') + 1

        return numberOfDifferentNodes

    # NOTE according to XML standard there can be ONLY ONE root node
    # so at first we selects all children of root (can be only one) and select first (can be only html)
    # then if there is other root-nodes they will appear in children of selected html-node
    # i.e:
    # <html>
    #   <head> ... </head>
    #   <body> ... </body>
    # <html>
    # <body>
    # </body>
    #
    # xmldata.xpath('/*')  - selects list with one html-node
    # xmldata,xpath('/*')[0].xpath('./*') - selects list with head, body and html node (!) (even there is body-tag)
    # xmldata,xpath('/*')[0].xpath('./*')[2].xpath('./*') - selects list with body-tag which is after html tag
    # we do not mention this in trees comparison, cause we search only mismatching
    # but this will help search out-of-place tags; not in place according DTD
    @staticmethod
    def printPagesPercentageMismatch(xmldataFirstPage, xmldataSecondPage):
        logger = logging.getLogger("printPagesPercentageMismatch")
        if xmldataFirstPage is None or xmldataSecondPage is None:
                logger.warning("Insufficient number of parameters")
                return
        pagesPercentageMismatch = htmlExtractor.getPagesPercentageMismatch(xmldataFirstPage, xmldataSecondPage)
        logger.info("\nPages percentage mismatch is: " + str(pagesPercentageMismatch * 100) + "%")
    #
    ###################################################################################################################

    # number of hidden tags
    def getTotalNumberOfHiddenTags(self):
        return self._xmldata.xpath('count(//*[%s = \'true\'])' % commonXPATHUtils.toLowerCase('@hidden', False))

    def printTotalNumberOfHiddenTags(self):
        logger = logging.getLogger(self.__class__.__name__)
        numberOfHiddenTags = self.getTotalNumberOfHiddenTags()
        if numberOfHiddenTags == 0:
            logger.warning("\nNone hidden tags")
            return

        logger.info("\nTotal number of hidden tags: " + str(numberOfHiddenTags))
    #
    ###################################################################################################################

    # number of script elements
    def getNumberOfScriptElements(self):
        numberOfInlineScriptElements = self._xmldata.xpath('count(//script[not(@src)])')
        numberOfIncludedScriptElements = self._xmldata.xpath('count(//script[@src])')
        return [numberOfInlineScriptElements, numberOfIncludedScriptElements]

    def getTotalNumberOfScriptElements(self):
        return sum(self.getNumberOfScriptElements())

    def printNumberOfScriptElements(self):
        logger = logging.getLogger(self.__class__.__name__)
        listOfScriptElements = self.getNumberOfScriptElements()
        if sum(listOfScriptElements) == 0:
            logger.warning("\nNone script elements")
            return

        logger.info("\nTotal number of script elements: " + str(sum(listOfScriptElements)))
        logger.info("Number of inline script elements: " + str(listOfScriptElements[0]))
        logger.info("Number of included script elements: " + str(listOfScriptElements[1]))
    #
    ###################################################################################################################

    # number of script-tags with src value and wrong extension of file
    # NOTE: see this: http://www.w3schools.com/tags/att_script_type.asp
    # and this: http://www.iana.org/assignments/media-types/media-types.xhtml#text
    # for all text script types

    # TODO ask: Is it valid to pass through elements like this:
    # <script type="text/javascript" src="http://s7.addthis.com/js/250/addthis_widget.js#pubid=ra-4f661ec623a400f0">
    def getNumberOfScriptElementsWithWrongFileExtension(self):
        #scriptTagTypeList = ['text/javascript', 'text/ecmascript', 'application/ecmascript', 'application/javascript',
        #                     'text/vbscript']
        dictOfScriptElements = {}

        # NOTE: there is no end-with() function in xPath 1.0, so you can use something like this:
        # $str2 = substring($str1, string-length($str1)- string-length($str2) +1)
        # will return true and false as result

        # for every script type attribute value check:
        # if attribute type match pattern
        #   attribute src exists and not empty
        #   attribute type value ends-with some extension
        # NOTE: cause both category and subcategory are case insensitive (as well as file extension) we use to_lower_case
        # xPath 1.0 wrappers

        # javascript
        dictOfScriptElements['text/javascript'] \
            = self._xmldata.xpath('count(//script[%s = \'text/javascript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.js',
                                                             False,
                                                             True)))
        dictOfScriptElements['application/javascript'] \
            = self._xmldata.xpath('count(//script[%s = \'application/javascript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.js',
                                                             False,
                                                             True)))
        dictOfScriptElements['default']\
            = self._xmldata.xpath('count(//script[not(@type)'
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                            '.js',
                                                            False,
                                                            True))

        # ecmascript
        dictOfScriptElements['text/ecmascript'] \
            = self._xmldata.xpath('count(//script[%s = \'text/ecmascript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.es',
                                                             False,
                                                             True)))
        dictOfScriptElements['application/ecmascript']\
            = self._xmldata.xpath('count(//script[%s = \'application/ecmascript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.es',
                                                             False,
                                                             True)))

        # vbscript
        # NOTE: possible file extensions (.vbs, .vbe, .wsf, .wsc), maybe some of them deprecated
        dictOfScriptElements['text/vbscript']\
            = self._xmldata.xpath('count(//script[%s = \'text/vbscript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.vbs',
                                                             False,
                                                             True)))
        dictOfScriptElements['text/vbscript'] \
            = self._xmldata.xpath('count(//script[%s = \'text/vbscript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.vbs',
                                                             False,
                                                             True)))
        dictOfScriptElements['text/vbscript'] \
            = self._xmldata.xpath('count(//script[%s = \'text/vbscript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.vbs',
                                                             False,
                                                             True)))
        dictOfScriptElements['text/vbscript'] \
            = self._xmldata.xpath('count(//script[%s = \'text/vbscript\''
                                 ' and boolean(@src)'
                                 ' and @src != ""'
                                 ' and not(%s)])'
                                 % (commonXPATHUtils.toLowerCase('@type', False),
                                    commonXPATHUtils.endWith(commonXPATHUtils.toLowerCase('@src', False),
                                                             '.vbs',
                                                             False,
                                                             True)))
        return dictOfScriptElements


    def getTotalNumberOfScriptElementsWithWrongFileExtension(self):
        return sum(self.getNumberOfScriptElementsWithWrongFileExtension().values())

    def printNumberOfScriptElementsWithWrongFileExtension(self):
        logger = logging.getLogger(self.__class__.__name__)
        dictOfScriptElementsWithWrongFileExtensions = self.getNumberOfScriptElementsWithWrongFileExtension()
        if sum(dictOfScriptElementsWithWrongFileExtensions.values()) == 0:
            logger.warning("\nNone script elements with wrong file extensions")
            return

        logger.info("\nTotal number of script elements with wrong file extensions: "
              + str(sum(dictOfScriptElementsWithWrongFileExtensions.values())))
        logger.info("Number of script elements with wrong file extensions:")
        for key, value in dictOfScriptElementsWithWrongFileExtensions.items():
            if value > 0:
                logger.info("script attribute type = " + str(key) + " - " + str(value))
    #
    ###################################################################################################################

    # number of characters in page
    # number of characters in text content of page
    def getNumberOfTextCharactersInPage(self):
        # get all text nodes except script nodes (in which we must delete all comments before take len() call
        # NOTE: we ignore embed script code inside <script> tags with @src attribute, cause it can't be executed
        listOfTextNodesExceptScript = self._xmldata.xpath('//*[name() != \'script\']/text()')
        numberOfCharactersInPage = 0
        for item in listOfTextNodesExceptScript:
            numberOfCharactersInPage += len(item)

        listOfInlineScriptTextNodes = self._xmldata.xpath('//script[not(@src)]/text()')
        for item in listOfInlineScriptTextNodes:
            # NOTE: only JS-comments
            # regexp for C/C++-like comments, also suitable for js-comments
            # ( /\* - begin C-like comment
            # [^\*/]* - everything except closing C-like comment 0+ times
            # \*/ - closing C-like comment
            # | - another part of regExp
            # // - begin of C++-like comment
            # .* - any symbol 0+ times
            # \n?) - until end of line, which can be off
            regExp = re.compile(r'(/\*[^\*/]*\*/|//.*\n?)')

            try:
                if self.getEncoding() is None:
                    tempItem = item
                else:
                    tempItem = item.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempItem = item.encode('utf-8')

            numberOfCharactersInPage = len(re.sub(regExp, '', str(tempItem)))

        return numberOfCharactersInPage

    # number of characters in page by xPath standards
    def getTotalNumberOfCharactersInPage(self):
        numberOfCharactersInPage = 0
        listOfAllNodes = self._xmldata.xpath('//*')
        for node in listOfAllNodes:
            # get node name; add 2 characters for open and close bracket
            # duplicate it for close tag, add 1 character for slash
            numberOfCharactersInPage += ((node.xpath('string-length(name(.))') + 2) * 2) + 1
            # get attribute values list
            listOfAllAttributes = node.xpath('./@*')
            # iteratively get attributes names (and it's length) and add attributes values length
            for i in range(0, len(listOfAllAttributes)):
                # add 1, cause xPath counts list elements from 1
                numberOfCharactersInPage += node.xpath('string-length(name(./@*[%d]))' % (i + 1))
                numberOfCharactersInPage += len(listOfAllAttributes[i])
        return numberOfCharactersInPage + self.getNumberOfTextCharactersInPage()

    # number of whitespace characters in page
    # NOTE: only in text() of nodes, cause xPath can't count space in tags
    def getNumberOfWhitespaceCharactersInPage(self):
        # like in getNumberOfTextCharactersInPage()
        listOfTextNodesExceptScript = self._xmldata.xpath('//*[name() != \'script\']/text()')
        numberOfCharactersInPage = 0
        for item in listOfTextNodesExceptScript:
            numberOfCharactersInPage += len(item.replace(" ", ""))

        listOfInlineScriptTextNodes = self._xmldata.xpath('//script[not(@src)]/text()')
        for item in listOfInlineScriptTextNodes:
            # additional '|\s' for replacing spaces in one turn
            regExp = re.compile(r'(/\*[^\*/]*\*/|//.*\n?|\s)')
            try:
                if self.getEncoding() is None:
                    tempItem = item
                else:
                    tempItem = item.encode(self.getEncoding())
            except Exception, error:
                logger = logging.getLogger(self.__class__.__name__)
                logger.warning(error)
                tempItem = item.encode('utf-8')

            numberOfCharactersInPage += len(re.sub(regExp, '', str(tempItem)))

        return numberOfCharactersInPage

    # print number of characters in the page
    def printNumberOfCharactersInPage(self):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nTotal number of text characters in page: " + str(self.getNumberOfTextCharactersInPage()))
        logger.info("Total number of characters in page: " + str(self.getTotalNumberOfCharactersInPage()))
        logger.info("Total number of whitespace characters in page: " + str(self.getNumberOfWhitespaceCharactersInPage()))
        logger.info("Total length of page: " + str(len(self._pageReady)))

    # - the percentage of unknown tags (impossible, case xpath can't see unknown tags)
    # NOTE but we can count number of characters of unknown tags (getFileLength() - getAllChars())
    # NOTE it is impossible to count exact number of html-content in page without ending or leading whitespaces
    # cause xPath can't count spaces in tags like '</h1                           >' and even in
    # '<h1             >'
    # Moreover xPath sees tags out-of-root html-tag as children of another html-tag as child of root html-tag
    # i.e
    # xmldata.xpath('/*')  - selects list with one html-node
    # xmldata,xpath('/*')[0].xpath('./*') - selects list with head, body and html node (!) (even there is body-tag)
    # xmldata,xpath('/*')[0].xpath('./*')[2].xpath('./*') - selects list with body-tag which is after html tag
    # so we have to monitor presence of another "real" html-tag
    # i.e
    # <html>
    #   <tag1> ... </tag1>
    # </html>
    # <html>
    #   <tag2> ... </tag2>
    # </html>
    # in this case if second 'html'-tag doesn't exist xPath still sees it. But if it doesn't have any attributes it's
    # very likely doesn't exists. We can manage this fact subtracting length of "fake" 'html'-tag from total file length,
    # thus it is likely not work cause xPath can't manage spaces (fake html-tag as well, i.e <html            >)
    #
    # TODO for correct file length recognition count both str(len(pageReady) and getTotalNumberOfCharactersInPage()
    # result, then choose lesser one
    #
    def printNumberOfUnknownCharacters(self):
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("Unknown tags, comments and unrecognized features length: " + str(len(self._pageReady) - self.getTotalNumberOfCharactersInPage()))
    #
    ###################################################################################################################

    # the percentage of unknown tags
    # unknown tags can be obtained via parsing %file_name% in XML format,
    # but it's difficult to make appropriate request (have to mention all known html tags);
    def getPercentageOfUnknownTags(self):
        if self.__openedAsXML == False:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("Object not opened as XML, can't count percentage of unknown tags")
            return None

        try:
            listOfAllHTMLTagNames = self.__configDict["html.all.tag.names"]
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            logger.warning("\nNone list of under-head-tag elements, can't perform analysis")
            return None

        expressionForAllNonHTMLNodes = ''
        for tagName in listOfAllHTMLTagNames:
            expressionForAllNonHTMLNodes += 'name() != \'' + tagName + '\' and '
        expressionForAllNonHTMLNodes = re.sub(' and $', '', expressionForAllNonHTMLNodes)
        return float(self._xmldata.xpath('count(//*)') - self._xmldata.xpath('count(//*[%s])' % expressionForAllNonHTMLNodes)) / self._xmldata.xpath('count(//*)')

    def printPercentageOfUnknownTags(self):
        logger = logging.getLogger(self.__class__.__name__)
        percentageOfUnknownTags = self.getPercentageOfUnknownTags()
        if percentageOfUnknownTags == None:
            logger.warning("\nImpossible to perform analysis (count percentage of unknown tags)")
            return

        logger.info("\nPercentage of unknown tags: " + str(percentageOfUnknownTags) + "%")
    #
    ###################################################################################################################

    # number of elements whose source is on an external domain
    def getNumberOfElementsWithExternalDomainSource(self):
        # in case of file analyzing we can't say anything about domain URI
        if not str(self._uri).startswith('http'):
            return []
        srcAttributeValuesList = self._xmldata.xpath('//*[@src]/@src')
        uriPathTillTDL = str(self._uri).split('/')[0] + '//' + str(self._uri).split('/')[2]
        numberOfElementsWithExternalDomainSource = 0
        for item in srcAttributeValuesList:
            # assume that external domain sources not starts with:
            # 1. full site-path like 'http(s)://path-till-slash'
            # 2. dot (.) as begin of relative path
            # 2. slash (/) as begin of relative path
            if not str(item).startswith(uriPathTillTDL)\
                and not str(item).startswith('.')\
                and not str(item).startswith('/'):
                numberOfElementsWithExternalDomainSource += 1
        # TODO check WHY this method returns 2 parameters
        return [len(srcAttributeValuesList), numberOfElementsWithExternalDomainSource]

    def getExternalDomainToInternalDomainSourceElementsRatio(self):
        resultList = self.getNumberOfElementsWithExternalDomainSource()
        if resultList == [] or resultList[0] == 0:
            return -1
        else:
            return float(resultList[1]) / resultList[0]

    def printNumberOfElementsWithExternalDomainSource(self):
        logger = logging.getLogger(self.__class__.__name__)
        resultList = self.getNumberOfElementsWithExternalDomainSource()
        if resultList != []:
            logger.info("\nNumber of elements with external domain source: "
                  + str(resultList[1]))
        else:
            logger.info("\nFile analyzing - no URI information")

    def printExternalDomainToInternalDomainSourceElementsRatio(self):
        logger = logging.getLogger(self.__class__.__name__)
        ratio = self.getExternalDomainToInternalDomainSourceElementsRatio()
        if ratio == -1:
            logger.info("\nFile analyzing - no URI information")
        else:
            logger.info("\nExternal domain to internal domain source elements ratio: " + str(ratio))
    #
    ###################################################################################################################

    # page hashing
    def getPageHashValues(self):
        try:
            if self.getEncoding() is None:
                pageHashSHA256 = hashlib.sha256(self._pageReady).hexdigest()
                pageHashSHA512 = hashlib.sha512(self._pageReady).hexdigest()
            else:
                pageHashSHA256 = hashlib.sha256(self._pageReady.encode(self.getEncoding())).hexdigest()
                pageHashSHA512 = hashlib.sha512(self._pageReady.encode(self.getEncoding())).hexdigest()
        except Exception, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning(error)
            pageHashSHA256 = hashlib.sha256(self._pageReady.encode('utf-8')).hexdigest()
            pageHashSHA512 = hashlib.sha512(self._pageReady.encode('utf-8')).hexdigest()


        return [pageHashSHA256, pageHashSHA512]

    def printPageHashValues(self):
        logger = logging.getLogger(self.__class__.__name__)
        pageHashValues = self.getPageHashValues()
        logger.info("\nPage hash (SHA-256): " + str(pageHashValues[0]))
        logger.info("Page hash (SHA-512): " + str(pageHashValues[1]))
    #
    ###################################################################################################################

    # public functions for outer packages
    # print result of all functions via reflection with default values
    # NOTE: no order in function calls
    def printAll(self, xmldata, pageReady, uri):
        logger = logging.getLogger(self.__class__.__name__)
        if xmldata is None or pageReady is None:
                logger.error("Insufficient number of parameters")
                return
        self.setXMLData(xmldata)
        self.setPageReady(pageReady)
        self._uri = uri
        if str(uri).lower().endswith(".xml"):
            self.__openedAsXML = True
        # FIXME remove in production
        #if(True):
        #    return
        logger.info("\n\nhtml Analyser ----------------------")
        begin = timeit.default_timer()
        for funcName, funcValue in htmlExtractor.__dict__.items():
            if str(funcName).startswith("print") and callable(funcValue):
                try:
                    getattr(self, funcName)()
                except Exception, error:
                    logger = logging.getLogger(self.__class__.__name__)
                    logger.exception(error)
                    pass
        end = timeit.default_timer()
        logger.info("\nElapsed time: " + str(end - begin) + " seconds")
        logger.info("----------------------------------------")
    #
    ###################################################################################################################

    # @queue parameters is needed for multiprocessing
    def getTotalAll(self, xmldata, pageReady, uri):
        if xmldata is None or pageReady is None:
                print("Insufficient number of parameters")
                return
        self.setXMLData(xmldata)
        self.setPageReady(pageReady)
        self._uri = uri
        resultDict = {}
        for funcName, funcValue in htmlExtractor.__dict__.items():
            if str(funcName).startswith("getTotal") and callable(funcValue):
                try:
                    resultDict[funcName] = getattr(self, funcName)()
                except Exception, error:
                    logger = logging.getLogger(self.__class__.__name__)
                    logger.exception(error)
                    pass

        return [resultDict, htmlExtractor.__name__]
    #
    ###################################################################################################################

    def getAllAnalyzeReport(self, **kwargs):
        try:
            kwargs['object']
        except KeyError, error:
            logger = logging.getLogger(self.__class__.__name__)
            logger.exception(error)
            logger.error("Insufficient number of parameters")
            return

        objectData = kwargs['object']
        if objectData.getXMLData() is None \
            or objectData.getPageReady() is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning('Error in input parameters:\n xmldata:\t%s\n pageReady:\t%s' % (objectData.getXMLData(),
                                                                                           objectData.getPageReady()))
            logger.warning("Insufficient number of parameters")
            return

        objectData = commonConnectionUtils.openPage(kwargs['uri'])
        self.setXMLData(objectData.getXMLData())
        self.setPageReady(objectData.getPageReady())
        self.setEncoding(objectData.getEncoding())
        self._uri = kwargs['uri']

        # get previous hash values, corresponding to this page
        connector = databaseConnector()
        register = modulesRegister()
        self.__listOfHashes = None
        previousHTMLFk = connector.select(register.getORMClass(configNames.page), ['htmlAnalysisFk'], 'url', self._uri)
        if previousHTMLFk:
            previousHashValuesFK = connector.select(register.getORMClass(self.__class__.__name__), ['hashValuesFk'],
                                                  configNames.id, previousHTMLFk[0].htmlAnalysisFk)
            previousHashValues = connector.select(register.getORMClass('hashValues'), None, configNames.id,
                                                  previousHashValuesFK[0].hashValuesFk)
            if previousHashValues is not None \
                and previousHashValues:
                self.__listOfHashes = [previousHashValues[0].hash256, previousHashValues[0].hash512]

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

        resultDict = {}
        # here we already performing analysis on page and can check need of analysis by
        # checking hash values <b> before </b> for-loops
        pageHashValues = getattr(self, self._scriptHashingFunctionName)()
        if self.__listOfHashes is not None and pageHashValues == self.__listOfHashes:
            # set id of this table row to which reference this listOfHashes
            resultDict[configNames.id] = previousHTMLFk[0].htmlAnalysisFk
            return [[resultDict], htmlExtractor.__name__]

        if numberOfProcesses > 1:
            numberOfFunctionsByProcess = len(self.__listOfAnalyzeFunctions) / numberOfProcesses
            functionsNotInProcesses = len(self.__listOfAnalyzeFunctions) % numberOfProcesses
            processQueue = Queue()
            proxyProcessesList = []
            resultDict = {}
            # start process for each function
            for i in xrange(0, numberOfFunctionsByProcess):
                for j in xrange(0, numberOfProcesses):
                    proxy = processProxy(None, [self, {},
                                                processQueue,
                                                self.__listOfAnalyzeFunctions[i * numberOfProcesses + j]],
                                        commonFunctions.callFunctionByNameQeued)
                    proxyProcessesList.append(proxy)
                    proxy.start()

                # wait for process joining
                #for j in xrange(0, len(proxyProcessesList)):
                #    proxyProcessesList[j].join()

                # gather all data
                for j in xrange(0, len(proxyProcessesList)):
                    functionCallResult = processQueue.get()
                    # if in result dict value = 0 - do not insert it
                    #if not ((type(functionCallResult[1]) is int and functionCallResult[1] == 0) or (type(
                    #        functionCallResult[1]) is float and functionCallResult[1] == 0.0)):
                    resultDict[functionCallResult[0]] = functionCallResult[1]

                del proxyProcessesList[:]

            # if reminder(number of functions, number of processes) != 0 - not all functions ran in separated processes
            # run other functions in one, current, process
            if functionsNotInProcesses != 0:
                for i in xrange(0, functionsNotInProcesses):
                    try:
                        functionCallResult = getattr(self, self.__listOfAnalyzeFunctions[-1 - i])()
                        # if in result dict value = 0 - do not insert it
                        #if not ((type(functionCallResult) is int and functionCallResult == 0) or (type(
                        #        functionCallResult) is float and functionCallResult == 0.0)):
                        resultDict[self.__listOfAnalyzeFunctions[-1 - i]] = functionCallResult
                    except Exception, error:
                        logger = logging.getLogger(self.__class__.__name__)
                        logger.exception(error)
                        pass

        else:
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
                    logger.info(self._uri)
                    pass

        # if we get here, so function calls above are correct and we can add hashes values to result dictionary
        # this values will be extract later
        hashValues = [{'hash256': pageHashValues[0], 'hash512': pageHashValues[1]}]
        resultDict['hashValues'] = hashValues

        return [[resultDict], htmlExtractor.__name__]
    #
    ###################################################################################################################

    #TODO list
    # - &lt; and others characters in comparing strings (?)
    # - DTD 4.01 strict and others; take a look over every tag in wc3 site and add its restrictions in code

    # http://www.ibm.com/developerworks/ru/library/x-hiperfparse/