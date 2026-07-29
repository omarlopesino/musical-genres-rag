"""Where a run's report is read.

A report is reached by its own URL rather than by a click, so an Airflow task can link the run it
just finished. The page the app navigates to and the page the API hands back are the same one, and
they say so from here rather than each from its own copy.
"""

REPORT_PATH = '/report'

# The chat is what the app opens on, so the evaluations moved off "/" and are linked back to by name
EVALUATIONS_PATH = '/evaluations'

"""Relative for the app serving the page, absolute for a caller that is somewhere else entirely"""
def reportUrl(id, baseUrl = ''):
    return '{base}{path}?run={id}'.format(
        base = baseUrl.rstrip('/'),
        path = REPORT_PATH,
        id = id,
    )
