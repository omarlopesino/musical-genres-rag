"""Where a run's report is read.

A report is reached by its own URL rather than by a click, so an Airflow task can link the run it
just finished. The page the app navigates to and the page the API hands back are the same one, and
they say so from here rather than each from its own copy.
"""

REPORT_PATH = '/report'

# The chat is what the app opens on, so the evaluations moved off "/" and are linked back to by name
EVALUATIONS_PATH = '/evaluations'

# Where the answers a judge has read are read back, all of them or one run's worth
JUDGEMENTS_PATH = '/judgements'

# What narrows the judgements to a run or to a single conversation. Written into the links below
# and read back off the url by the page itself, so both ends name it from here.
BATCH_PARAM = 'batch'
CONVERSATION_PARAM = 'conversation'

"""Relative for the app serving the page, absolute for a caller that is somewhere else entirely"""
def reportUrl(id, baseUrl = ''):
    return '{base}{path}?run={id}'.format(
        base = baseUrl.rstrip('/'),
        path = REPORT_PATH,
        id = id,
    )

"""The same page a judge run links to, narrowed to the answers that run read"""
def judgementsUrl(batch, baseUrl = ''):
    return _narrowedJudgements(BATCH_PARAM, batch, baseUrl)

"""The same page again, narrowed to the feedback left on one conversation"""
def feedbackUrl(conversation, baseUrl = ''):
    return _narrowedJudgements(CONVERSATION_PARAM, conversation, baseUrl)

def _narrowedJudgements(parameter, id, baseUrl):
    return '{base}{path}?{parameter}={id}'.format(
        base = baseUrl.rstrip('/'),
        path = JUDGEMENTS_PATH,
        parameter = parameter,
        id = id,
    )
