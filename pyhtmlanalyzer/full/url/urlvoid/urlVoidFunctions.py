import logging
from pyhtmlanalyzer.commonFunctions.commonConnectionUtils import commonConnectionUtils
from pyhtmlanalyzer.full.commonURIAnalysisData import commonURIAnalysisData

__author__ = 'hokan'

class urlVoidFunctions(commonURIAnalysisData):
    __API_KEY = '395dd4d82fe6737fa60192e61ecde31a7774f6d3'
    __pageData = None

    def __init__(self, uri = None):
        commonURIAnalysisData.__init__(self, uri)
        if uri is not None:
            self.retrieveURLData()

    def retrieveURLData(self):
        if self._uri is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("URI is not set")
            return

        if self.getRemainedQueries() == 0:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("No URLVoid queries remain")
            return

        result = commonConnectionUtils.openPage('http://api.urlvoid.com/api1000/'
                                                       + self.__API_KEY
                                                       + '/host/'
                                                       + self._uri.split('://')[1].split('/')[0].lstrip('www.'))

        # if there exists any info about site (details tag exists) - save it
        if len(result.getXMLData().xpath('//details')) != 0:
            self.__pageData = result.getXMLData()

    def getRemainedQueries(self):
        remainedQueries = commonConnectionUtils.openPage('http://api.urlvoid.com/api1000/'
                                                         + self.__API_KEY
                                                         + '/stats/remained/')
        if remainedQueries is None \
            or remainedQueries == []:
            return 0

        return remainedQueries.getXMLData().xpath('//queriesremained/text()')[0]

    def getIsHostMalicious(self):
        if self._uri is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("URI is not set")
            return None

        if self.__pageData is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("No URLVoid info about this URI")
            return None

        return True if self.__pageData.xpath('//count/text()')[0] != 0 else False

    def printIsHostMalicious(self):
        isHostMalicious = self.getIsHostMalicious()
        if isHostMalicious is None:
            return

        logger = logging.getLogger(self.__class__.__name__)
        logger.info("Host is " + ('not' if isHostMalicious is False else '') + 'malicious')

    def getDetectedEnginesList(self):
        if self._uri is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("URI is not set")
            return None

        if self.__pageData is None:
            logger = logging.getLogger(self.__class__.__name__)
            logger.warning("No URLVoid info about this URI")
            return None

        return self.__pageData.xpath('//engine/text()')

    def printDetectedEngines(self):
        detectedEnginesList = self.getDetectedEnginesList()
        if detectedEnginesList is None:
            return

        logger = logging.getLogger(self.__class__.__name__)
        logger.info("\nList of engines assuming host malicious:")
        for engine in detectedEnginesList:
            logger.info("\t" + engine)