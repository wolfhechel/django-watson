from django.core.management.commands.shell import Command as BaseCommand
from django.db.models.loading import get_models
import code
import os

class Command(BaseCommand):
    def handle_noargs(self, **options):
        # XXX: (Temporary) workaround for ticket #1796: force early loading of all
        # models from installed apps.
        models = get_models()

        use_plain = options.get('plain', False)
        interface = options.get('interface', None)

        try:
            if use_plain:
                # Don't bother loading IPython, because the user wants plain Python.
                raise ImportError

            self.run_shell(shell=interface)
        except ImportError:
            import code
            # Set up a dictionary to serve as the environment for the shell, so
            # that tab completion works on objects that are imported at runtime.
            # See ticket 5082.
            imported_objects = {}

            for model in models:
                imported_objects[model.__name__] = model

            try:  # Try activating rlcompleter, because it's handy.
                import readline
            except ImportError:
                pass
            else:
                # We don't have to wrap the following import in a 'try', because
                # we already know 'readline' was imported successfully.
                import rlcompleter
                readline.set_completer(rlcompleter.Completer(imported_objects).complete)
                readline.parse_and_bind("tab:complete")

            # We want to honor both $PYTHONSTARTUP and .pythonrc.py, so follow system
            # conventions and get $PYTHONSTARTUP first then .pythonrc.py.
            if not use_plain:
                for pythonrc in (os.environ.get("PYTHONSTARTUP"),
                                 os.path.expanduser('~/.pythonrc.py')):
                    if pythonrc and os.path.isfile(pythonrc):
                        try:
                            with open(pythonrc) as handle:
                                exec(compile(handle.read(), pythonrc, 'exec'))
                        except NameError:
                            pass
            code.interact(local=imported_objects)
