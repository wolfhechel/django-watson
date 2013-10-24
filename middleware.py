import sys
import string
import json
import pydoc

from code import InteractiveInterpreter

from django.utils.crypto import get_random_string
from django.http.response import HttpResponseServerError, HttpResponse
from django.views.debug import ExceptionReporter
from django.template import Context, loader
from django.conf import settings
from django.core.context_processors import csrf

from .utils.io import stdout_as_stringio

class InteractiveExceptionReporter(ExceptionReporter):

    secret = None

    def __init__(self, request, exc_type, exc_value, tb):
        ExceptionReporter.__init__(self, request, exc_type, exc_value, tb)

    def get_traceback_html(self):
        "Return HTML version of debug 500 HTTP error page."
        template = loader.get_template('technical_500.html')
        context = Context(self.get_traceback_data())

        return template.render(context)

    def collect_frames(self):
        frames = {}

        tb = self.tb

        while tb is not None:

            # Support for __traceback_hide__ which is used by a few libraries
            # to hide internal frames.
            if tb.tb_frame.f_locals.get('__traceback_hide__'):
                tb = traceback.tb_next
                continue

            frames[id(tb)] = tb.tb_frame

            tb = tb.tb_next

        return frames


class InteractiveConsole(InteractiveInterpreter, object):

    __instances__ = {}

    globals = None

    frame = None

    preserved_source = ""

    def __init__(self, frame):
        super(InteractiveConsole, self).__init__(frame.f_locals.copy())

        frame.f_globals.update({
            'help' : self.help,
            'reset' : self.reset
        })

        self.globals = frame.f_globals.copy()

        self.frame = frame

    @staticmethod
    def help(object=None):
        if object is not None:
            return pydoc.help(object)

        print 'The interactive help tool has been disabled in this console.'

    def reset(self):
        self.locals.clear()
        self.locals.update(self.frame.f_locals)

        self.globals.clear()
        self.globals.update(self.frame.f_globals)

    def runsource(self, source, filename="<input>", symbol="single"):
        if self.preserved_source:
            source = self.preserved_source + source

        if source.strip() == 'reset':
            source = source.replace('reset', 'reset()')

        with stdout_as_stringio() as output:
            multiline = super(InteractiveConsole, self).runsource(source, filename, symbol)

        if multiline:
            self.preserved_source = source + '\n'
        else:
            self.preserved_source = ""

        return (multiline, output.getvalue()[:-1])

    def runcode(self, code):
        try:
            exec code in self.globals, self.locals
        except Exception:
            self.showtraceback()

    def write(self, data):
        sys.stdout.write(data)

    @staticmethod
    def execute(frame, command):
        frame_id = id(frame)

        if frame_id not in InteractiveConsole.__instances__:
            InteractiveConsole.__instances__[frame_id] = InteractiveConsole(frame)

        console_instance = InteractiveConsole.__instances__[frame_id]

        return console_instance.runsource(command)


class InteractiveDebuggerMiddleware(object):

    frames = None

    def __init__(self):
        self.frames = {}

    def test_usability(self, request):
        return not (request.environ['wsgi.multiprocess'] or not settings.DEBUG)


    def process_request(self, request):
        if self.test_usability(request) is False:
            return

        debugging = request.POST.get('__debugging__', None)

        if debugging:
            success = False
            error = data = None

            command = request.POST.get('command', '')
            frame_id = int(request.POST.get('frame', 0))

            if frame_id in self.frames:
                success = True
                frame = self.frames[frame_id]

                multiline, data = self.run_code(command, frame)

            response = json.dumps({
                'success' : success,
                'error' : error,
                'data' : data,
                'multiline' : multiline
            })

            return HttpResponse(response, content_type="application/json")

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Reset frames and secret before processing a new view
        self.frames = {}

    def process_exception(self, request, exception):
        if self.test_usability(request) is False:
            return

        exc_type, exc_value, tb = sys.exc_info()

        # If we're getting an exception that does not match the most recent caught one
        # we'll be unable to handle it, since we require the traceback.
        if type(exception) is not exc_type:
            return None

        reporter = InteractiveExceptionReporter(request, exc_type, exc_value, tb)

        self.frames = reporter.collect_frames()

        if request.is_ajax():
            output = reporter.get_traceback_text()
            mimetype = 'text/plain'
        else:
            output = reporter.get_traceback_html()
            mimetype = 'text/html'

        return HttpResponseServerError(output, content_type=mimetype)

    def run_code(self, code, frame):
        return InteractiveConsole.execute(frame, code)