#
#    Guernsey - Library to simplify creating REST web services using Python and Twisted
#    Copyright (C) 2014 Magine Sweden AB
#    Copyright (C) 2016 Ingemar Nilsson
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

#
# This module provides a convenient base class for REST resource
# classes built using twisted.web.
#

from twisted.web import resource, server
from twisted.internet import reactor, error
from twisted.python import log as twistedlog

import guernsey.util as util
import guernsey.web.json as json
import guernsey.web.model as gwm
import guernsey.db as db

import logging, os, sys

class Resource(resource.Resource):
    #
    # Public options
    #
    templatePath = "."
    disableLibraryTemplates = False
    corsAllowOrigins = []
    corsAllowMethods = []
    logger = None
    contentTypeProducers = None
    templateSearchPath = None
    _maxResourceDepth = 50
    _libraryPath = os.path.abspath(os.path.dirname(__file__))
    _libraryTemplatePath = os.path.join(_libraryPath, ".templates")
    _appName = "Resource"
    _templateName = None

    def __init__(self, parent=None, root=None):
        resource.Resource.__init__(self)
        self.parent = parent
        self.root = root
        if not self.__class__.logger:
            self.__class__.logger = util.getLogger(self)
        self.contentTypeProducers = {"text/html": self.__getHtml,
                                     "application/xhtml+xml": self.__getHtml,
                                     "application/json": self.__getJson,
                                     "*/*": self.__getHtml}
        self.templateSearchPath = [ self.templatePath ]
        if not self.disableLibraryTemplates:
            self.templateSearchPath += [self._libraryTemplatePath, self._libraryPath]

    def getParent(self):
        return self.parent

    def getRoot(self):
        depth = 0
        if not self.root:
            p = self
            while p.getParent() != None and depth < self._maxResourceDepth:
                if p is p.getParent():
                    self.logger.error("Loop in resource parent link. "
                                      "Parent link points back to this resource.")
                    return None
                p = p.getParent()
                depth += 1
            if isinstance(p, RootResource):
                return p
            elif depth >= self._maxResourceDepth:
                self.logger.error("Possible loop in resource parent links, aborting search")
                return None
            else:
                return None
        return self.root

    def setTemplateName(self, templateName):
        self._templateName = templateName

    def addContentTypeProducer(self, contentType, producer):
        self.contentTypeProducers[contentType] = producer

    def removeContentTypeProducer(self, contentType):
        if self.contentTypeProducer.get(contentType):
            del self.contentTypeProducer[contentType]

    def _getDefaultTemplateFilename(self):
        return self.__class__.__name__ + ".tmpl"

    def _findTemplateInSearchPath(self, tmplRelPath):
        self.logger.debug("_findTemplateInSearchPath(%r)", tmplRelPath)
        for path in self.templateSearchPath:
            templateFile = os.path.join(path, tmplRelPath)
            self.logger.debug("Checking template file %r", templateFile)
            if os.path.isfile(templateFile):
                return templateFile
        return None

    def fillTemplate(self, model, templateFile=None, request=None):
        self.logger.debug("fillTemplate(%r, %r, %r)", model, templateFile, request)

        class MissingTemplateError(Exception):
            def __init__(self, searchPath, filename):
                self.searchPath = searchPath
                self.filename = filename

            def __str__(self):
                return "No template file %r found in search path %r" \
                    % (self.filename, self.searchPath)

            def __repr__(self):
                return "MissingTemplateError(%r, %r)" % (self.searchPath, self.filename)

        if not templateFile:
            self.logger.debug("Template file not passed as argument, checking template name")
            templateName = self._templateName
            if not templateName:
                self.logger.debug("Template name not specified, using default template name")
                templateName = self._getDefaultTemplateFilename()
            self.logger.debug("Looking up template in search path")
            templateFile = self._findTemplateInSearchPath(templateName)

        if templateFile:
            self.logger.info("Using template file %r", templateFile)
            from Cheetah.Template import Template

            def lookupTemplate(tmplRelPath):
                self.logger.debug("lookupTemplate(%r)", tmplRelPath)
                _templateFile = self._findTemplateInSearchPath(tmplRelPath)
                if _templateFile:
                    return _templateFile
                else:
                    raise MissingTemplateError(self.templateSearchPath,
                                               tmplRelPath)

            def resolveUrl(url):
                return self.resolveUrl(str(request.URLPath()), url)

            self.logger.debug("Template model: %r", model)
            template = Template(file=templateFile,
                                searchList=[model, {"lookupTemplate": lookupTemplate,
                                                    "resolveUrl": resolveUrl,
                                                    "appName": self._appName}])
            return str(template)
        else:
            if templateName:
                templateFile = templateName
            else:
                templateFile = self._getDefaultTemplateFilename()
            self.logger.warning("No template file '%s' found in search path",
                                templateFile)
            self.logger.warning("Template Search Path:")
            if self.logger.isEnabledFor(logging.WARNING):
                for path in self.templateSearchPath:
                    self.logger.warning("\t%s", path)
            raise MissingTemplateError(self.templateSearchPath,
                                       templateFile)

    def __getHtml(self, request):
        res = self.getHtml(request)
        if res is server.NOT_DONE_YET:
            return res
        if type(res) == str:
            return res
        return self.fillTemplate(res, request=request)

    def getHtml(self, request):
        return "<html>Hello HTML: %s</html>\n" % self.__class__.__name__

    def __getJson(self, request):
        res = self.getJson(request)
        if res is server.NOT_DONE_YET:
            return res
        if type(res) == str:
            return res
        if res == None:
            return ""
        return json.dumps(res) + "\n"

    def getJson(self, request):
        msg = "Hello JSON: %s" % self.__class__.__name__
        return json.dumps({"message": msg})

    def checkAccept(self, request, contentType, allowWildcard=False):
        self.logger.debug("checkAccept(%r, %r)", request, contentType)
        acceptTypes = self.getAccepts(request)
        
        for quality, mediaType in acceptTypes:
            if contentType == mediaType:
                self.logger.debug("Accepts %r", contentType)
                return True
            if mediaType == "*/*" and allowWildcard:
                self.logger.debug("Accepts %r (*/*)", contentType)
                return True
        self.logger.debug("Does not accepts %r", contentType)
        return False

    def acceptsJson(self, request):
        return self.checkAccept(request, "application/json")

    def getAccepts(self, request):
        self.logger.debug("getAccepts(%r)", request)
        accepts = request.getHeader("Accept").split(",")
        self.logger.debug("Media Types accepted by client: %r", accepts)
        
        acceptTypes = []
        for accept in accepts:
            mediaType, param = map(lambda x: x.strip(), accept.partition(";")[::2])
            if param:
                k, v = param.partition("=")[::2]
                if k == "q":
                    quality = float(v)
            else:
                quality = float(1)
            acceptTypes.append((quality, mediaType))
        return sorted(acceptTypes, key=lambda x: x[0], reverse=True)

    def performContentNegotiation(self, request):
        self.logger.debug("performContentNegotiation(%r)", request)
        acceptTypes = self.getAccepts(request)
        self.logger.debug("Media Types accepted by client (parsed): %r", acceptTypes)
        
        for quality, mediaType in acceptTypes:
            self.logger.debug("Checking producer for media type: %r", mediaType)
            producer = self.contentTypeProducers.get(mediaType)
            if producer:
                self.logger.debug("Found producer for mediaType: %r, %r", mediaType, producer)
                request.setHeader("Content-Type", mediaType)
                return producer(request)
        self.notAcceptable(request)
        return " "

    def render_GET(self, request):
        self.logger.debug("render_GET(%r)", request)
        if not request.path.endswith("/"):
            return self.redirectWithEndingSlash(request)

        request.setHeader("Cache-Control", "no-cache")

        return self.performContentNegotiation(request)

    def getChild(self, name, request):
        if name == '':
            return self
        return resource.Resource.getChild(self, name, request)

    def _logRequestHeaders(self, request):
        self.logger.debug("Request headers:")
        if self.logger.isEnabledFor(logging.DEBUG):
            for k, v in request.requestHeaders.getAllRawHeaders():
                self.logger.debug("\t%s: %s", k, v)

    def _logResponseHeaders(self, request):
        self.logger.debug("Response headers:")
        if self.logger.isEnabledFor(logging.DEBUG):
            for k, v in request.responseHeaders.getAllRawHeaders():
                self.logger.debug("\t%s: %s", k, v)

    def render(self, request):
        self.logger.info("render(%r)" % request)
        self.logger.debug("request.method: %s", request.method)
        self.logger.debug("request.URLPath(): %s", request.URLPath())
        self.logger.debug("request.uri: %s", request.uri)
        self.logger.debug("request.path: %s", request.path)

        self._logRequestHeaders(request)
        self.logger.debug("Client IP: %s", request.getClientIP())
        self.logger.debug("request.getHost(): %s", request.getHost())
        self.logger.debug("request.getRequestHostname(): %s", request.getRequestHostname())

        from twisted.web import http
        if request.method == "PUT" and len(request.args) == 0:
            request.args = http.parse_qs(request.content.read(), 1)

        if request.getHeader("Origin"):
            result = self.handleCors(request)
            if result:
                return result

        response = None
        try:
            response = resource.Resource.render(self, request)
        except:
            self.logger.exception("Exception during resource rendering")
            raise
        self._logResponseHeaders(request)
        return response

    def handleCors(self, request):
        """Handle CORS (Cross-Origin Resource Sharing) requests"""
        self.logger.info("handleCors(%r)", request)
        self.logger.debug("Origin header found, checking allowed URLs.")

        if not self.corsAllowOrigins:
            self.logger.info("No CORS allowed origin URLs found.")
            return

        self.logger.debug("Allowed origin URL Patterns:")
        if self.logger.isEnabledFor(logging.DEBUG):
            for urlPattern in self.corsAllowOrigins:
                self.logger.debug("\t%s", urlPattern)

        origin = request.getHeader("Origin")
        import re
        for urlPattern in self.corsAllowOrigins:
            match = re.search(urlPattern, origin)
            if match:
                self.logger.info("Match found, allowing access for CORS request.")
                request.setHeader("Access-Control-Allow-Origin", origin)
                request.setHeader("Access-Control-Expose-Headers", "Content-Length")
                if request.method == "OPTIONS":
                    return self.handleCorsPreFlight(request)
                return

        self.logger.info("No match found, denying access for CORS request.")

    def handleCorsPreFlight(self, request):
        self.logger.info("OPTIONS request detected, checking allowed methods")
        self.logger.debug("Allowed request methods:")
        if self.logger.isEnabledFor(logging.DEBUG):
            for method in self.corsAllowMethods:
                self.logger.debug("\t%s", method)

        acrm = request.getHeader("Access-Control-Request-Method")
        if acrm and acrm.upper() in self.corsAllowMethods:
            self.logger.info("Request method allowed, enabling access")
            request.setHeader("Access-Control-Allow-Methods",
                              ", ".join(self.corsAllowMethods))
            request.setHeader("Access-Control-Max-Age", "3600")
        else:
            self.logger.info("Request method not allowed, disabling access")
            self.forbidden(request)
            self._logResponseHeaders(request)
            return " "

        acrh = request.getHeader("Access-Control-Request-Headers")
        if acrh:
            request.setHeader("Access-Control-Allow-Headers", acrh)

        self.success(request)
        self._logResponseHeaders(request)
        return " "

    def cleanPostData(self, request, convertToCamelCase=False, convertBool=False):
        args = {}
        for k, v in request.args.iteritems():
            if convertToCamelCase:
                k = util.convertToCamelCase(k)
            if type(v) == list and len(v) == 1:
                v = v[0]
            if convertBool:
                if v.lower() in ["true", "yes"]:
                    v = True
                elif v.lower() in ["false", "no"]:
                    v = False
            args[k] = v

        return args

    def resolveUrl(self, baseUrl, relativeUrl):
        import urlparse
        return urlparse.urljoin(baseUrl, relativeUrl)

    def setLocation(self, request, url):
        self.setLocationAbs(request, self.resolveUrl(str(request.URLPath()), url))

    def setLocationAbs(self, request, url):
        request.setHeader("Location", url)

    def success(self, request):
        request.setResponseCode(200)

    def created(self, request):
        request.setResponseCode(201)

    def noContent(self, request):
        request.setResponseCode(204)

    def seeOther(self, request, url):
        request.setResponseCode(303)
        self.setLocation(request, url)

    def badRequest(self, request):
        request.setResponseCode(400)

    def forbidden(self, request):
        request.setResponseCode(403)

    def notFound(self, request):
        request.setResponseCode(404)

    def notAcceptable(self, request):
        request.setResponseCode(406)

    def serverError(self, request):
        request.setResponseCode(500)

    def redirectWithEndingSlash(self, request):
        self.logger.debug("request.URLPath(): %s", request.URLPath())
        self.logger.debug("request.uri: %s", request.uri)
        self.logger.debug("request.path: %s", request.path)

        path, queryParams = request.uri.partition("?")[::2]
        self.logger.debug("path: %s", path)
        self.logger.debug("queryParams: %s", queryParams)

        if queryParams:
            newUrl = "/?".join([str(request.URLPath()), queryParams])
        else:
            newUrl = str(request.URLPath()) + "/"
        self.logger.debug("newUrl: %s", newUrl)
        request.setResponseCode(302)
        self.setLocationAbs(request, newUrl)
        return ""


class ConfigVariable(object):
    def __init__(self, name, defaultValue="", desc=""):
        self.name = name
        self.value = defaultValue
        self.desc = desc

    def getName(self):
        return self.name

    def getValue(self):
        return self.value

    def getDescription(self):
        if self.desc:
            return self.desc
        else:
            return self.name
    
    def setValue(self, value):
        self.value = value

    def renderHtml(self):
        return self.value

    def __repr__(self):
        return "%s(%r, %r, %r)" % (self.__class__.__name__,
                                   self.name,
                                   self.value,
                                   self.desc)

    def __json__(self):
        return self.__dict__

class ConfigString(ConfigVariable):
    def renderHtml(self):
        return '<input type="text" id="config-%(name)s" name="%(name)s" value="%(value)s" size="50" />' % {"name": self.name, "value": self.value}

class ConfigReadOnly(ConfigVariable):
    def renderHtml(self):
        return self.value

class ConfigPassword(ConfigVariable):
    def renderHtml(self):
        return '<input type="password" id="config-%(name)s" name="%(name)s" value="%(value)s" size="50" />' % {"name": self.name, "value": self.value}

class ConfigEnum(ConfigVariable):
    allowedValues = None

    def __init__(self, name, defaultValue="", allowedValues=[], desc=""):
        ConfigVariable.__init__(self, name, defaultValue, desc)
        self.allowedValues = allowedValues

    def setValue(self, value):
        if value not in self.allowedValues:
            raise ValueError("Tried to set value not in list of allowed values")
        self.value = value

    def renderHtml(self):
        html = '<select id="config-%(name)s" name="%(name)s">' % {"name": self.name}
        for av in self.allowedValues:
            if av == self.value:
                selected = 'selected="selected"'
            else:
                selected = ""
            html += '<option value="%(value)s" %(selected)s>%(value)s</option>' \
                % {"value": av, "selected": selected}
        return html + "</select>"

    def __repr__(self):
        return "%s(%r, %r, %r, %r)" % (self.__class__.__name__,
                                       self.name,
                                       self.value,
                                       self.desc,
                                       self.allowedValues)


class ConfigModel(object):
    variables = None

    def __init__(self):
        self.variables = {}

    def addVariable(self, variable):
        self.variables[variable.name] = variable

    def itervalues(self):
        return self.variables.itervalues()

    def iteritems(self):
        return self.variables.iteritems()

    def get(self, key):
        if key not in self.variables:
            raise AttributeError("Config variable %s not found" % key)
        return self.variables.get(key).getValue()

    def set(self, key, value):
        if key not in self.variables:
            raise AttributeError("Config variable %s not found" % key)
        self.variables[key].setValue(value)

    def isReadOnly(self, key):
        if isinstance(self.variables.get(key), ConfigReadOnly):
            return True
        else:
            return False

    def __contains__(self, key):
        return key in self.variables

    def __json__(self):
        return self.__dict__

#
# Database resource base classes
#

class DatabaseResource(Resource):
    def __init__(self, tableName, parent):
        Resource.__init__(self, parent)
        self.__tableName = tableName

    def getDatabase(self):
        return self.getRoot().database

    def getTable(self):
        return getattr(self.getDatabase(), self.__tableName)

class DatabaseCollectionResource(DatabaseResource):
    def __init__(self, entityResourceClass, tableName, parent):
        DatabaseResource.__init__(self, tableName, parent)
        self.__entityResourceClass = entityResourceClass

    def getChild(self, name, request):
        if len(name) > 0:
            return self.__entityResourceClass(name, self)
        else:
            return DatabaseResource.getChild(self, name, request)

    def getEntityCollection(self, applyFilters=True, resultType=list):
        parent = self.getParent()
        if applyFilters and parent and hasattr(parent, "getFilter"):
            filterFunc = parent.getFilter()
            return resultType(filterFunc(self.getTable().iteritems()))
        else:
            return resultType(self.getTable().iteritems())

class DatabaseEntityResource(DatabaseResource):
    pass

#
# Issue-related model and database classes
#

class IssueModel(gwm.Model):
    level = None
    message = None
    resourcePath = None
    callStack = None
    exception = None
    timestamp = None

    def __init__(self, level, message, resourcePath=None, callStack=None, exception=None):
        gwm.Model.__init__(self)
        self.level = level
        self.message = message
        self.resourcePath = resourcePath
        self.callStack = callStack
        self.exception = exception
        self.timestamp = datetime.datetime.utcnow()

    def __json__(self):
        i = copy.deepcopy(self)
        if i:
            if i.timestamp:
                i.timestamp = i.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return i.__dict__

class IssueTable(db.Table):
    def __init__(self):
        db.Table.__init__(self, "issues")
        self.maxId = 0

    def __setstate__(self, state):
        db.Table.__setstate__(self, state)
        self.logger.debug("__setstate__(...)")
        if not hasattr(self, "maxId"):
            self.maxId = 0

    def add(self, model):
        issueId = self.maxId
        self.maxId += 1
        self.update(str(issueId), model, createIfNotFound=True)
        return issueId

#
# Database class
#

class Database(db.Database):
    def __init__(self):
        db.Database.__init__(self)
        self.issues = IssueTable()

    def __setstate__(self, state):
        db.Database.__setstate__(self, state)
        if not hasattr(self, "issues"):
            self.logger.debug("Attribute 'issues' not found, adding to database")
            self.issues = IssueTable()
        elif not self.issues:
            self.logger.debug("No issue table found, adding to database")
            self.issues = IssueTable()

class TwistedLoggingObserver(twistedlog.PythonLoggingObserver):
    # This method is a modified version of
    # twisted.python.log.PythonLoggingObserver.emit()
    def emit(self, eventDict):
        if 'logLevel' in eventDict:
            level = eventDict['logLevel']
        elif eventDict['isError']:
            level = logging.ERROR
        else:
            level = logging.DEBUG
            eventDict['logLevel'] = level
            twistedlog.PythonLoggingObserver.emit(self, eventDict)

class RootResource(Resource):
    options = None
    _numericLogLevel = None
    _numericLogLevelConsole = None
    _instance = None
    database = None
    databaseClass = Database
    appName = None

    # Log handlers
    __memoryHandler = None
    __fileHandler = None
    __streamHandler = None

    # OptionParser variables, override as necessary
    version = "[Program version]"
    desc = "[Program description]"
    usage = "[Program usage]"

    def __init__(self, appName=None, options=None, appId=None):
        self.__class__.logger = util.getLogger(self)
        self.__class__._instance = self

        self.appName = appName
        self.appId = appId

        args = None
        if not options:
            self.options, self.args = self.__parseArgs()
        else:
            self.options = options

        if not self.options.showDb:
            self.config = ConfigModel()
            self.config.addVariable(ConfigEnum("logLevel", self.options.logLevelFile.upper(),
                                               ["DEBUG",
                                                "INFO",
                                                "WARNING",
                                                "ERROR",
                                                "CRITICAL"],
                                               "Log Level"))
            self.config.addVariable(ConfigString("logFormat",
                                                 "%(asctime)s %(levelname)s %(name)s: "
                                                 "%(message)s",
                                                 "Log Format String"))

            self.setupLogging()

            self.__shutdownHooks = []
            reactor.addSystemEventTrigger("before", "shutdown",
                                          self.__beforeShutdownCallback)
            self.addShutdownHook(logging.shutdown)
            if self.appName:
                self.addShutdownHook(self.logger.info, "Stopped: %s", self.appName)
            # These events fire, but are not likely to complete. We
            # allow using them, but consider yourself warned. We'll
            # keep the call in case an update fixes it.
            #
            # Note: No logging calls allowed in these callbacks, as
            #       the logging subsystem has already been shutdown.
            reactor.addSystemEventTrigger("during", "shutdown",
                                          self.__duringShutdownCallback)
            reactor.addSystemEventTrigger("after", "shutdown",
                                          self.__afterShutdownCallback)
            
            if self.appName:
                self.logger.warning("Starting: %s", self.appName)
                reactor.callWhenRunning(self.logger.info, "Started: %s", self.appName)

            Resource.templatePath = self.options.templatePath
            Resource.disableLibraryTemplates = self.options.disableLibraryTemplates
            if self.appName:
                Resource._appName = self.appName
            if hasattr(self.options, "corsAllowOrigins"):
                Resource.corsAllowOrigins = self.options.corsAllowOrigins
            if hasattr(self.options, "corsAllowMethods"):
                Resource.corsAllowMethods = map(lambda x: x.upper(),
                                                self.options.corsAllowMethods) \
                    + ["GET", "HEAD", "POST"]
            Resource.__init__(self)
    
            import twisted.web.static as static
            
            self.putChild("css", static.File(os.path.join(self.options.templatePath, "css")))
            self.putChild("js", static.File(os.path.join(self.options.templatePath, "js")))
            self.putChild("images", static.File(os.path.join(self.options.templatePath,
                                                             "images")))

            if not self.disableLibraryTemplates:
                self.putChild("libcss",
                              static.File(os.path.join(self._libraryTemplatePath, "css")))
                self.putChild("libjs",
                              static.File(os.path.join(self._libraryTemplatePath, "js")))
                self.putChild("libimages",
                              static.File(os.path.join(self._libraryTemplatePath, "images")))
    
            self.putChild("config", ConfigResource(self))
            self.putChild("issues", Issues(self))

        if self.options.dbFile and os.path.exists(self.options.dbFile):
            self.logger.info("Loading database from file %s", self.options.dbFile)
            self.database = self.databaseClass.load(self.options.dbFile)
            if not self.database.__class__ is self.databaseClass:
                self.logger.warning("Database class is '%s.%s' instead of expected '%s.%s'",
                                    self.database.__class__.__module__,
                                    self.database.__class__.__name__,
                                    self.databaseClass.__module__,
                                    self.databaseClass.__name__)
            if self.options.showDb:
                print "Database: %r" % self.database
                sys.exit(0)
        else:
            if self.options.showDb:
                print "Database file '%s' not found!" % self.options.dbFile
                sys.exit(1)
            else:
                self.database = self.databaseClass()
                
        if self.options.dbFile:
            self.addShutdownHook(self._saveDatabase)
            if self.options.dbSaveInterval > 0:
                self.logger.info("Scheduling database save procedure every %s seconds",
                                 self.options.dbSaveInterval)
                from twisted.internet import task
                t = task.LoopingCall(self._saveDatabase)
                t.start(self.options.dbSaveInterval, now=False)

        if self.appName:
            self.addShutdownHook(self.logger.warning, "Stopping: %s", self.appName)

    def _saveDatabase(self):
        self.logger.info("Saving database to file '%s'", self.options.dbFile) 
        self.database.save(self.options.dbFile)

    def getAppId(self):
        if self.options:
            return self.options.appId
        elif self.appId:
            return self.appId
        else:
            import random, string
            return self.__class__.__name__ + "." \
                + ''.join(random.choice(string.ascii_lowercase) for _ in range(10))

    def setupLogging(self):
        import os, logging.handlers
        from twisted.python import log

        observer = TwistedLoggingObserver()
        observer.start()

        rootLogger = logging.getLogger()
        filePath = os.path.join(self.options.logDir, self.getAppId() + ".log")
        self.__fileHandler \
            = logging.handlers.RotatingFileHandler(filePath,
                                                   maxBytes=self.options.logFileMaxSize,
                                                   backupCount=self.options.logFileMaxBackups,
                                                   delay=True)
        self.__fileHandler.setLevel(self._numericLogLevel)
        self.__fileHandler.setFormatter(logging.Formatter(self.config.get("logFormat")))

        # Do not open log file as root when intending to drop privileges later
        if os.getuid() == 0 and self.options.user:
            self.__memoryHandler = logging.handlers.MemoryHandler(1048576,
                                                                  target=self.__fileHandler)
            rootLogger.addHandler(self.__memoryHandler)
        else:
            rootLogger.addHandler(self.__fileHandler)

        self.__streamHandler = logging.StreamHandler()
        self.__streamHandler.setLevel(self._numericLogLevelConsole)
        self.__streamHandler.setFormatter(logging.Formatter(self.config.get("logFormat")))
        rootLogger.addHandler(self.__streamHandler)
        rootLogger.setLevel(min(self._numericLogLevel, self._numericLogLevelConsole))

    def resetLogging(self):
        self.logger.debug("resetLogging()")
        self._numericLogLevel = getattr(logging, self.config.get("logLevel").upper(), None)
        if logging.root:
            if self.__memoryHandler:
                self.__memoryHandler.close()
                self.__memoryHandler = None
            if self.__fileHandler:
                self.__fileHandler.close()
                self.__fileHandler = None
            if self.__streamHandler:
                self.__streamHandler.close()
                self.__streamHandler = None
            del logging.root.handlers[:]
        self.setupLogging()

    def __duringShutdownCallback(self):
        pass

    def __afterShutdownCallback(self):
        pass

    def addShutdownHook(self, func, *args, **kwargs):
        self.__shutdownHooks.insert(0, (func, args, kwargs))

    def __beforeShutdownCallback(self):
        self.logger.debug("Running shutdown hooks")
        while len(self.__shutdownHooks) > 0:
            func, args, kwargs = self.__shutdownHooks.pop(0)
            if hasattr(func, "im_class"):
                # This is a bound method
                hookName = "%s.%s.%s" % (func.im_class.__module__,
                                         func.im_class.__name__,
                                         func.im_func.__name__)
            else:
                # This is an ordinary function
                hookName = "%s.%s" % (func.__module__, func.__name__)
            self.logger.debug("Calling shutdown hook: %s", hookName)
            func(*args, **kwargs)

    def listenOnFreePort(self, portBase, factory):
        self.logger.debug("listenOnFreePort(%r, %r)", portBase, factory)
        port = portBase
        while True:
            try:
                listeningPort = reactor.listenTCP(port, factory)
                self.logger.debug("Found free port %r to listen on", port)
                return port, listeningPort
            except error.CannotListenError, e:
                port += 1

    @classmethod
    def getInstance(cls):
        return cls._instance

    def createIssue(self, level, message, resource=None, saveCallStack=True, exception=None):
        if resource:
            resourcePath = []
            while True:
                if hasattr(resource, "getId"):
                    resourceId = resource.getId()
                elif hasattr(resource, "id"):
                    resourceId = resource.id
                elif hasattr(resource, "name"):
                    resourceId = resource.name
                else:
                    resourceId = None
                resourcePath.insert(0, "%s{id: %s}" % (resource.__class__.__name__, resourceId))
                if isinstance(resource, RootResource):
                    break
                resource = resource.getParent()
            resourcePath = " -> ".join(resourcePath)
        else:
            resourcePath = ""

        if saveCallStack:
            import traceback
            callStack = []
            for line in traceback.format_stack():
                callStack.append(line.strip())
            callStack = "\n".join(callStack)
        else:
            callStack = ""

        issue = IssueModel(level, message, resourcePath, callStack)
        self.database.issues.add(issue)

    def addConfigVariable(self, variable):
        self.config.addVariable(variable)

    def getHostName(self):
        import socket
        return socket.gethostname()

    def getCanonicalUrl(self):
        return "http://%s:%s/" % (self.getHostName(), self.options.port)

    def getHtml(self, request):
        return self.fillTemplate({})

    def updateConfig(self, config, updateAll=True):
        self.logger.debug("updateConfig(%r, %r)", config, updateAll)
        if updateAll:
            for key, value in config.iteritems():
                self.logger.debug("Checking config variable %r", key)
                if key in self.config:
                    self.logger.debug("Variable found, setting value %r", value)
                    self.config.set(key, value)
                else:
                    self.logger.debug("Variable not found, ignoring")
        self.resetLogging()

    def optparsePostInit(self, parser):
        # Override this if you want to add extra command-line options.
        # You can also override this to set other default values for
        # already defined options.
        pass

    def optparsePostParse(self, parser, options, args):
        # Override this if you want to post-process parsed options and
        # arguments, e.g. check validity of supplied options.
        pass

    def __parseArgs(self):
        import optparse
    
        parser = optparse.OptionParser(version = self.version,
                                       description = self.desc,
                                       usage = self.usage,
                                       conflict_handler = "resolve")
        parser.add_option("--log-level-file", action="store", type="str",
                          dest="logLevelFile", metavar="LEVEL",
                          help="Log level to use for file logging (Default: %default)")
        parser.add_option("--log-level-console", action="store", type="str",
                          dest="logLevelConsole", metavar="LEVEL",
                          help="Log level to use for console logging(Default: %default)")
        parser.add_option("--log-dir", action="store", type="str",
                          dest="logDir", metavar="PATH",
                          help="Log directory to use (Default: %default)")
        parser.add_option("--log-file-max-size", action="store", type="str",
                          dest="logFileMaxSize", metavar="SIZE",
                          help="Log file max size before rotation (Supports k/K/M postfixes)" \
                          " (Default: %default)")
        parser.add_option("--log-file-max-backups", action="store", type="int",
                          dest="logFileMaxBackups", metavar="INTEGER",
                          help="Number of log file backups to keep (Default: %default)")
        parser.add_option("--app-id", action="store", type="str",
                          dest="appId", metavar="IDENTIFIER",
                          help="Application identifier. Used e.g. for log file name. " \
                          "(Default: %default)")
        parser.add_option("-p", "--port", action="store", type="int",
                          dest="port", metavar="PORT",
                          help="Port to listen on (Default: %default)")
        parser.add_option("--extra-port", action="append", type="int",
                          dest="extraPorts", metavar="PORT",
                          help="Extra port to listen on. Multiple instances of this option " \
                              + "can be specified")
        parser.add_option("-t", "--template-path", action="store", type="str",
                          dest="templatePath", metavar="PATH",
                          help="Path to template files (Default: %default)")
        parser.add_option("--disable-library-templates", action="store_true",
                          dest="disableLibraryTemplates",
                          help="Disable use of library-supplied template files "
                          "(Default: %default)")
        parser.add_option("--cors-allow-origin", action="append", type="str",
                          dest="corsAllowOrigins", metavar="URL",
                          help="Allowed origin URL pattern for CORS requests. Multiple " \
                              + "instances of this option can be supplied.")
        parser.add_option("--cors-allow-method", action="append", type="str",
                          dest="corsAllowMethods", metavar="METHOD",
                          help="Allowed method for CORS requests (GET, HEAD and POST does " \
                              + "not need to be specified). Multiple instances of this " \
                              + "option can be supplied.")
        parser.add_option("-u", "--user", action="store", type="str",
                          dest="user", metavar="USER",
                          help="Run daemon as a specified user " \
                              "(Only useful if started as root)")
        parser.add_option("-g", "--group", action="store", type="str",
                          dest="group", metavar="GROUP",
                          help="Run daemon as a specified group " \
                              "(Only useful if started as root)")
        parser.add_option("-f", "--dbfile", action="store", type="str",
                          dest="dbFile", metavar="FILE",
                          help="Database file name (Default: [in-memory database])")
        parser.add_option("--db-save-interval", action="store", type="int",
                          dest="dbSaveInterval", metavar="SECONDS",
                          help="Database save interval (0 = Off) "
                          "(Default: Off)")
        parser.add_option("--show-db", action="store_true", dest="showDb",
                          help="Just display the contents of the database (Default: %default)")
        parser.set_defaults(logLevelFile="WARNING")
        parser.set_defaults(logLevelConsole="WARNING")
        parser.set_defaults(logDir="/tmp")
        parser.set_defaults(logFileMaxSize="10M")
        parser.set_defaults(logFileMaxBackups=5)
        parser.set_defaults(appId=self.getAppId())
        parser.set_defaults(port=8080)
        parser.set_defaults(extraPorts=[])
        parser.set_defaults(templatePath="templates")
        parser.set_defaults(disableLibraryTemplates=False)
        parser.set_defaults(corsAllowOrigins=[])
        parser.set_defaults(corsAllowMethods=[])
        parser.set_defaults(user=None)
        parser.set_defaults(group=None)
        parser.set_defaults(dbFile=None)
        parser.set_defaults(dbSaveInterval=0)
        parser.set_defaults(showDb=False)

        self.optparsePostInit(parser)
        options, args = parser.parse_args()
        
        self._numericLogLevel = getattr(logging, options.logLevelFile.upper(), None)
        if not isinstance(self._numericLogLevel, int):
            parser.error("Invalid file log level: %s" % options.logLevelFile)
        self._numericLogLevelConsole = getattr(logging, options.logLevelConsole.upper(), None)
        if not isinstance(self._numericLogLevelConsole, int):
            parser.error("Invalid console log level: %s" % options.logLevelConsole)

        if os.getuid() != 0:
            if options.user:
                parser.error("Cannot set user when running as non-root user")
            if options.group:
                parser.error("Cannot set group when running as non-root user")

        if options.user and not options.group or options.group and not options.user:
            parser.error("You need to specify both user and group, if specified at all")

        if options.logFileMaxSize[-1] == "M":
            size = int(options.logFileMaxSize[:-1]) * 1048576
        elif options.logFileMaxSize[-1].upper() == "K":
            size = int(options.logFileMaxSize[:-1] * 1024)
        else:
            size = int(options.logFileMaxSize)
        options.logFileMaxSize = size

        self.optparsePostParse(parser, options, args)

        return options, args

    def listen(self, site, ports, ignore=[]):
        import itertools
        listenPorts = map(lambda x: x[0], itertools.groupby(sorted(ports)))

        for port in listenPorts:
            if port not in ignore:
                reactor.listenTCP(port, site)

    def _dropPrivileges(self, user, group):
        import pwd, grp

        # Get the uid/gid from the name
        runningUid = pwd.getpwnam(user).pw_uid
        runningGid = grp.getgrnam(group).gr_gid
        
        # Remove group privileges
        os.setgroups([])
        
        # Try setting the new uid/gid
        os.setgid(runningGid)
        os.setuid(runningUid)

        # Reset logging
        self.resetLogging()
        
    def run(self):
        self.listen(server.Site(self), [self.options.port] + self.options.extraPorts)

        if self.options.user and self.options.group:
            self._dropPrivileges(self.options.user, self.options.group)

        reactor.run()

class ConfigResource(Resource):
    def __init__(self, parent):
        Resource.__init__(self, parent)

    def getModel(self):
        return self.getParent().config

    def getHtml(self, request):
        return {"config": self.getModel()}

    def getJson(self, request):
        return self.getModel().variables

    def render_POST(self, request):
        self.logger.debug("render_POST(%r)", request)
        args = self.cleanPostData(request, convertToCamelCase=True, convertBool=True)
        self.logger.debug("args: %r", args)
        filteredArgs = {}
        for key, value in args.iteritems():
            self.logger.debug("key, value = %r, %r", key, value)
            if key not in self.getParent().config:
                self.logger.debug("Key not in config model")
                self.badRequest(request)
                return ("Configuration key '%s' does not match any online-configurable " \
                    + "config variable.") % key
            if not self.getParent().config.isReadOnly(key):
                filteredArgs[key] = value
            else:
                self.logger.debug("Configuration variable '%s' is readonly. Ignoring variable.",
                                  key)
        self.parent.updateConfig(filteredArgs)
        self.seeOther(request, "")
        return ""

#
# Issue-related resource classes
#

class Issues(DatabaseCollectionResource):
    def __init__(self, parent):
        DatabaseCollectionResource.__init__(self, Issue, "issues", parent)

    def getHtml(self, request):
        issues = []
        for issueId, issue in sorted(self.getTable().iteritems(),
                                     key=lambda x: x[1].timestamp, reverse=True):
            issue.id = issueId
            issue.url = self.resolveUrl(str(request.URLPath()), str(issue.id))
            issues.append(issue)
        return {"issues": issues}

    def getJson(self, request):
        return self.getTable().getAll()

class Issue(DatabaseEntityResource):
    def __init__(self, id, parent):
        DatabaseEntityResource.__init__(self, "issues", parent)
        self.id = id

    def getHtml(self, request):
        i = self.getTable().get(self.id)
        if i:
            issue = i
        else:
            self.notFound(request)
            issue = IssueModel()
        issue.found = bool(i)
        issue.id = self.id
        return {"issue": issue}

    def getJson(self, request):
        h = self.getTable().get(self.id)
        if not h:
            self.notFound(request)
        return h

    def render_DELETE(self, request):
        if self.id == "all":
            self.deleteAllIssues()
            self.success(request)
        elif self.getTable().get(self.id):
            self.deleteIssue()
            self.success(request)
        else:
            self.notFound(request)
        return ""

    def deleteAllIssues(self):
        self.getTable().clear()

    def deleteIssue(self):
        self.getTable().delete(self.id)
