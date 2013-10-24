import sys
from contextlib import contextmanager

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

__author__ = 'jonet'

@contextmanager
def stdout_as_stringio():
    old = sys.stdout

    sys.stdout = StringIO()

    yield sys.stdout

    sys.stdout = old