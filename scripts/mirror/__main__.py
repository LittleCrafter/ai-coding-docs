"""Allow ``python -m mirror``.

This file exists solely so the package can be executed as a module::

    python -m mirror --dry-run

Python looks for ``__main__.py`` inside a package when it is invoked with
``-m``; without it, ``python -m mirror`` would fail even though the real
entry point (:func:`mirror.cli.main`) is perfectly importable.

It deliberately contains no logic of its own: it delegates straight to the
same :func:`mirror.cli.main` used by the ``mirror-docs`` console script, so
both invocation styles always behave identically. ``main()`` returns an int
exit code, and ``raise SystemExit(...)`` forwards that code to the shell
(0 = success), which is what cron jobs and CI pipelines key off.
"""

from .cli import main

if __name__ == "__main__":
    # This guard is always true for `python -m mirror`; it exists so that
    # importing this module has no side effects.
    raise SystemExit(main())
